import os, os.path
import base64
import hmac
import hashlib
import httplib
import logging
from logging import debug, info, warning, error
from stat import ST_SIZE

from Utils import *
from SortedDict import SortedDict
from BidirMap import BidirMap
from ConfigParser import ConfigParser

class Config(object):
	_instance = None
	_parsed_files = []
	access_key = ""
	secret_key = ""
	host = "s3.amazonaws.com"
	verbosity = logging.WARNING
	send_chunk = 4096
	recv_chunk = 4096
	human_readable_sizes = False
	force = False
	show_uri = False
	acl_public = False

	## Creating a singleton
	def __new__(self, configfile = None):
		if self._instance is None:
			self._instance = object.__new__(self)
		return self._instance

	def __init__(self, configfile = None):
		if configfile:
			self.read_config_file(configfile)

	def option_list(self):
		retval = []
		for option in dir(self):
			## Skip attributes that start with underscore or are not string, int or bool
			option_type = type(getattr(Config, option))
			if option.startswith("_") or \
			   not (option_type in (
			   		type("string"),	# str
			        	type(42),	# int
					type(True))):	# bool
				continue
			retval.append(option)
		return retval

	def read_config_file(self, configfile):
		cp = ConfigParser(configfile)
		for option in self.option_list():
			self.update_option(option, cp.get(option))
		self._parsed_files.append(configfile)

	def update_option(self, option, value):
		if value is None:
			return
		#### Special treatment of some options
		## verbosity must be known to "logging" module
		if option == "verbosity":
			try:
				setattr(Config, "verbosity", logging._levelNames[value])
			except KeyError:
				error("Config: verbosity level '%s' is not valid" % value)
		## allow yes/no, true/false, on/off and 1/0 for boolean options
		elif type(getattr(Config, option)) is type(True):	# bool
			if str(value).lower() in ("true", "yes", "on", "1"):
				setattr(Config, option, True)
			elif str(value).lower() in ("false", "no", "off", "0"):
				setattr(Config, option, False)
			else:
				error("Config: value of option '%s' must be Yes or No, not '%s'" % (option, value))
		elif type(getattr(Config, option)) is type(42):		# int
			try:
				setattr(Config, option, int(value))
			except ValueError, e:
				error("Config: value of option '%s' must be an integer, not '%s'" % (option, value))
		else:							# string
			setattr(Config, option, value)

class S3Error (Exception):
	def __init__(self, response):
		self.status = response["status"]
		self.reason = response["reason"]
		debug("S3Error: %s (%s)" % (self.status, self.reason))
		if response.has_key("headers"):
			for header in response["headers"]:
				debug("HttpHeader: %s: %s" % (header, response["headers"][header]))
		if response.has_key("data"):
			tree = ET.fromstring(response["data"])
			for child in tree.getchildren():
				if child.text != "":
					debug("ErrorXML: " + child.tag + ": " + repr(child.text))
					self.__setattr__(child.tag, child.text)

	def __str__(self):
		retval = "%d (%s)" % (self.status, self.reason)
		try:
			retval += (": %s" % self.Code)
		except AttributeError:
			pass
		return retval

class ParameterError(Exception):
	pass

class S3:
	http_methods = BidirMap(
		GET = 0x01,
		PUT = 0x02,
		HEAD = 0x04,
		DELETE = 0x08,
		MASK = 0x0F,
		)
	
	targets = BidirMap(
		SERVICE = 0x0100,
		BUCKET = 0x0200,
		OBJECT = 0x0400,
		MASK = 0x0700,
		)

	operations = BidirMap(
		UNDFINED = 0x0000,
		LIST_ALL_BUCKETS = targets["SERVICE"] | http_methods["GET"],
		BUCKET_CREATE = targets["BUCKET"] | http_methods["PUT"],
		BUCKET_LIST = targets["BUCKET"] | http_methods["GET"],
		BUCKET_DELETE = targets["BUCKET"] | http_methods["DELETE"],
		OBJECT_PUT = targets["OBJECT"] | http_methods["PUT"],
		OBJECT_GET = targets["OBJECT"] | http_methods["GET"],
		OBJECT_HEAD = targets["OBJECT"] | http_methods["HEAD"],
		OBJECT_DELETE = targets["OBJECT"] | http_methods["DELETE"],
	)

	codes = {
		"NoSuchBucket" : "Bucket '%s' does not exist",
		"AccessDenied" : "Access to bucket '%s' was denied",
		"BucketAlreadyExists" : "Bucket '%s' already exists",
		}

	def __init__(self, config):
		self.config = config

	def list_all_buckets(self):
		request = self.create_request("LIST_ALL_BUCKETS")
		response = self.send_request(request)
		response["list"] = getListFromXml(response["data"], "Bucket")
		return response
	
	def bucket_list(self, bucket, prefix = None):
		## TODO: use prefix if supplied
		request = self.create_request("BUCKET_LIST", bucket = bucket)
		response = self.send_request(request)
		debug(response)
		response["list"] = getListFromXml(response["data"], "Contents")
		return response

	def bucket_create(self, bucket):
		self.check_bucket_name(bucket)
		request = self.create_request("BUCKET_CREATE", bucket = bucket)
		response = self.send_request(request)
		return response

	def bucket_delete(self, bucket):
		request = self.create_request("BUCKET_DELETE", bucket = bucket)
		response = self.send_request(request)
		return response

	def object_put(self, filename, bucket, object):
		if not os.path.isfile(filename):
			raise ParameterError("%s is not a regular file" % filename)
		try:
			file = open(filename, "r")
			size = os.stat(filename)[ST_SIZE]
		except IOError, e:
			raise ParameterError("%s: %s" % (filename, e.strerror))
		headers = SortedDict()
		headers["content-length"] = size
		if self.config.acl_public:
			headers["x-amz-acl"] = "public-read"
		request = self.create_request("OBJECT_PUT", bucket = bucket, object = object, headers = headers)
		response = self.send_file(request, file)
		response["size"] = size
		return response

	def object_get(self, filename, bucket, object):
		try:
			file = open(filename, "w")
		except IOError, e:
			raise ParameterError("%s: %s" % (filename, e.strerror))
		request = self.create_request("OBJECT_GET", bucket = bucket, object = object)
		response = self.recv_file(request, file)
		response["size"] = int(response["headers"]["content-length"])
		return response

	def object_delete(self, bucket, object):
		request = self.create_request("OBJECT_DELETE", bucket = bucket, object = object)
		response = self.send_request(request)
		return response

	def create_request(self, operation, bucket = None, object = None, headers = None):
		resource = "/"
		if bucket:
			resource += str(bucket)
			if object:
				resource += "/"+str(object)

		if not headers:
			headers = SortedDict()

		if headers.has_key("date"):
			if not headers.has_key("x-amz-date"):
				headers["x-amz-date"] = headers["date"]
			del(headers["date"])
		
		if not headers.has_key("x-amz-date"):
			headers["x-amz-date"] = time.strftime("%a, %d %b %Y %H:%M:%S %z", time.gmtime(time.time()))

		method_string = S3.http_methods.getkey(S3.operations[operation] & S3.http_methods["MASK"])
		signature = self.sign_headers(method_string, resource, headers)
		headers["Authorization"] = "AWS "+self.config.access_key+":"+signature
		return (method_string, resource, headers)
	
	def send_request(self, request):
		method_string, resource, headers = request
		info("Processing request, please wait...")
		conn = httplib.HTTPConnection(self.config.host)
		conn.request(method_string, resource, {}, headers)
		response = {}
		http_response = conn.getresponse()
		response["status"] = http_response.status
		response["reason"] = http_response.reason
		response["headers"] = convertTupleListToDict(http_response.getheaders())
		response["data"] =  http_response.read()
		conn.close()
		if response["status"] < 200 or response["status"] > 299:
			raise S3Error(response)
		return response

	def send_file(self, request, file):
		method_string, resource, headers = request
		info("Sending file '%s', please wait..." % file.name)
		conn = httplib.HTTPConnection(self.config.host)
		conn.connect()
		conn.putrequest(method_string, resource)
		for header in headers.keys():
			conn.putheader(header, str(headers[header]))
		conn.endheaders()
		size_left = size_total = headers.get("content-length")
		while (size_left > 0):
			debug("SendFile: Reading up to %d bytes from '%s'" % (self.config.send_chunk, file.name))
			data = file.read(self.config.send_chunk)
			debug("SendFile: Sending %d bytes to the server" % len(data))
			conn.send(data)
			size_left -= len(data)
			info("Sent %d bytes (%d %% of %d)" % (
				(size_total - size_left),
				(size_total - size_left) * 100 / size_total,
				size_total))
		response = {}
		http_response = conn.getresponse()
		response["status"] = http_response.status
		response["reason"] = http_response.reason
		response["headers"] = convertTupleListToDict(http_response.getheaders())
		response["data"] =  http_response.read()
		conn.close()
		if response["status"] < 200 or response["status"] > 299:
			raise S3Error(response)
		return response

	def recv_file(self, request, file):
		method_string, resource, headers = request
		info("Receiving file '%s', please wait..." % file.name)
		conn = httplib.HTTPConnection(self.config.host)
		conn.connect()
		conn.putrequest(method_string, resource)
		for header in headers.keys():
			conn.putheader(header, str(headers[header]))
		conn.endheaders()
		response = {}
		http_response = conn.getresponse()
		response["status"] = http_response.status
		response["reason"] = http_response.reason
		response["headers"] = convertTupleListToDict(http_response.getheaders())
		if response["status"] < 200 or response["status"] > 299:
			raise S3Error(response)

		md5=hashlib.new("md5")
		size_left = size_total = int(response["headers"]["content-length"])
		while (size_left > 0):
			this_chunk = size_left > self.config.recv_chunk and self.config.recv_chunk or size_left
			debug("ReceiveFile: Receiving up to %d bytes from the server" % this_chunk)
			data = http_response.read(this_chunk)
			debug("ReceiveFile: Writing %d bytes to file '%s'" % (len(data), file.name))
			file.write(data)
			md5.update(data)
			size_left -= len(data)
			info("Received %d bytes (%d %% of %d)" % (
				(size_total - size_left),
				(size_total - size_left) * 100 / size_total,
				size_total))
		conn.close()
		response["md5"] = md5.hexdigest()
		response["md5match"] = response["headers"]["etag"].find(response["md5"]) >= 0
		debug("ReceiveFile: Computed MD5 = %s" % response["md5"])
		if not response["md5match"]:
			warning("MD5 signatures do not match: computed=%s, received=%s" % (
				response["md5"], response["headers"]["etag"]))

		return response

	def sign_headers(self, method, resource, headers):
		h  = method+"\n"
		h += headers.get("content-md5", "")+"\n"
		h += headers.get("content-type", "")+"\n"
		h += headers.get("date", "")+"\n"
		for header in headers.keys():
			if header.startswith("x-amz-"):
				h += header+":"+str(headers[header])+"\n"
		h += resource
		return base64.encodestring(hmac.new(self.config.secret_key, h, hashlib.sha1).digest()).strip()

	def check_bucket_name(self, bucket):
		if re.compile("[^A-Za-z0-9\._-]").search(bucket):
			raise ParameterError("Bucket name '%s' contains unallowed characters" % bucket)
		if len(bucket) < 3:
			raise ParameterError("Bucket name '%s' is too short (min 3 characters)" % bucket)
		if len(bucket) > 255:
			raise ParameterError("Bucket name '%s' is too long (max 255 characters)" % bucket)
		return True

	def compose_uri(self, bucket, object = None, force_uri = False):
		if self.config.show_uri or force_uri:
			uri = "s3://" + bucket
			if object:
				uri += "/"+object
			return uri
		else:
			return object and object or bucket

	def parse_s3_uri(self, uri):
		match = re.compile("^s3://([^/]*)/?(.*)").match(uri)
		if match:
			return (True,) + match.groups()
		else:
			return (False, "", "")

