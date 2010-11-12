#!/usr/bin/perl

# Format s3cmd.1 manpage
# Usage:
#   s3cmd --help | format-manpage.pl > s3cmd.1

use strict;

my $commands = "";
my $cfcommands = "";
my $options = "";

while (<>) {
	if (/^Commands:/) {
		while (<>) {
			last if (/^\s*$/);
			my ($desc, $cmd, $cmdline);
			($desc = $_) =~ s/^\s*(.*?)\s*$/$1/;
			($cmdline = <>) =~ s/^\s*s3cmd (.*?) (.*?)\s*$/s3cmd \\fB$1\\fR \\fI$2\\fR/;
			$cmd = $1;
			if ($cmd =~ /^cf/) {
				$cfcommands .= ".TP\n$cmdline\n$desc\n";
			} else {
				$commands .= ".TP\n$cmdline\n$desc\n";
			}
		}
	}
	if (/^Options:/) {
		my ($opt, $desc);
		while (<>) {
			last if (/^\s*$/);
			$_ =~ s/\s*(.*?)\s*$/$1/;
			$desc = "";
			$opt = "";
			if (/^(-.*)/) {
				$opt = $1;
				if ($opt =~ /  /) {
					($opt, $desc) = split(/\s\s+/, $opt, 2);
				}
				$opt =~ s/(-[^ ,=]+)/\\fB$1\\fR/g;
				$opt =~ s/-/\\-/g;
				$options .= ".TP\n$opt\n";
			} else {
				$desc .= $_;
			}
			if ($desc) {
				$options .= "$desc\n";
			}
		}
	}
}
print "
.TH s3cmd 1
.SH NAME
s3cmd \\- tool for managing Amazon S3 storage space and Amazon CloudFront content delivery network
.SH SYNOPSIS
.B s3cmd
[\\fIOPTIONS\\fR] \\fICOMMAND\\fR [\\fIPARAMETERS\\fR]
.SH DESCRIPTION
.PP
.B s3cmd
is a command line client for copying files to/from 
Amazon S3 (Simple Storage Service) and performing other
related tasks, for instance creating and removing buckets,
listing objects, etc.

.SH COMMANDS
.PP
.B s3cmd
can do several \\fIactions\\fR specified by the following \\fIcommands\\fR.
$commands

.PP
Commands for CloudFront management
$cfcommands

.SH OPTIONS
.PP
Some of the below specified options can have their default 
values set in 
.B s3cmd
config file (by default \$HOME/.s3cmd). As it's a simple text file 
feel free to open it with your favorite text editor and do any
changes you like. 
$options

.SH EXAMPLES
One of the most powerful commands of \\fIs3cmd\\fR is \\fBs3cmd sync\\fR used for 
synchronising complete directory trees to or from remote S3 storage. To some extent 
\\fBs3cmd put\\fR and \\fBs3cmd get\\fR share a similar behaviour with \\fBsync\\fR.
.PP
Basic usage common in backup scenarios is as simple as:
.nf
	s3cmd sync /local/path/ s3://test-bucket/backup/
.fi
.PP
This command will find all files under /local/path directory and copy them 
to corresponding paths under s3://test-bucket/backup on the remote side.
For example:
.nf
	/local/path/\\fBfile1.ext\\fR         \\->  s3://bucket/backup/\\fBfile1.ext\\fR
	/local/path/\\fBdir123/file2.bin\\fR  \\->  s3://bucket/backup/\\fBdir123/file2.bin\\fR
.fi
.PP
However if the local path doesn't end with a slash the last directory's name
is used on the remote side as well. Compare these with the previous example:
.nf
	s3cmd sync /local/path s3://test-bucket/backup/
.fi
will sync:
.nf
	/local/\\fBpath/file1.ext\\fR         \\->  s3://bucket/backup/\\fBpath/file1.ext\\fR
	/local/\\fBpath/dir123/file2.bin\\fR  \\->  s3://bucket/backup/\\fBpath/dir123/file2.bin\\fR
.fi
.PP
To retrieve the files back from S3 use inverted syntax:
.nf
	s3cmd sync s3://test-bucket/backup/ /tmp/restore/
.fi
that will download files:
.nf
	s3://bucket/backup/\\fBfile1.ext\\fR         \\->  /tmp/restore/\\fBfile1.ext\\fR       
	s3://bucket/backup/\\fBdir123/file2.bin\\fR  \\->  /tmp/restore/\\fBdir123/file2.bin\\fR
.fi
.PP
Without the trailing slash on source the behaviour is similar to 
what has been demonstrated with upload:
.nf
	s3cmd sync s3://test-bucket/backup /tmp/restore/
.fi
will download the files as:
.nf
	s3://bucket/\\fBbackup/file1.ext\\fR         \\->  /tmp/restore/\\fBbackup/file1.ext\\fR       
	s3://bucket/\\fBbackup/dir123/file2.bin\\fR  \\->  /tmp/restore/\\fBbackup/dir123/file2.bin\\fR
.fi
.PP
All source file names, the bold ones above, are matched against \\fBexclude\\fR 
rules and those that match are then re\\-checked against \\fBinclude\\fR rules to see
whether they should be excluded or kept in the source list.
.PP
For the purpose of \\fB\\-\\-exclude\\fR and \\fB\\-\\-include\\fR matching only the 
bold file names above are used. For instance only \\fBpath/file1.ext\\fR is tested
against the patterns, not \\fI/local/\\fBpath/file1.ext\\fR
.PP
Both \\fB\\-\\-exclude\\fR and \\fB\\-\\-include\\fR work with shell-style wildcards (a.k.a. GLOB).
For a greater flexibility s3cmd provides Regular-expression versions of the two exclude options 
named \\fB\\-\\-rexclude\\fR and \\fB\\-\\-rinclude\\fR. 
The options with ...\\fB\\-from\\fR suffix (eg \\-\\-rinclude\\-from) expect a filename as
an argument. Each line of such a file is treated as one pattern.
.PP
There is only one set of patterns built from all \\fB\\-\\-(r)exclude(\\-from)\\fR options
and similarly for include variant. Any file excluded with eg \\-\\-exclude can 
be put back with a pattern found in \\-\\-rinclude\\-from list.
.PP
Run s3cmd with \\fB\\-\\-dry\\-run\\fR to verify that your rules work as expected. 
Use together with \\fB\\-\\-debug\\fR get detailed information
about matching file names against exclude and include rules.
.PP
For example to exclude all files with \".jpg\" extension except those beginning with a number use:
.PP
	\\-\\-exclude '*.jpg' \\-\\-rinclude '[0-9].*\\.jpg'

.SH SEE ALSO
For the most up to date list of options run 
.B s3cmd \\-\\-help
.br
For more info about usage, examples and other related info visit project homepage at
.br
.B http://s3tools.org

.SH AUTHOR
Written by Michal Ludvig <mludvig\@logix.net.nz>
.SH CONTACT, SUPPORT
Prefered way to get support is our mailing list:
.I s3tools\\-general\@lists.sourceforge.net
.SH REPORTING BUGS
Report bugs to 
.I s3tools\\-bugs\@lists.sourceforge.net
.SH COPYRIGHT
Copyright \\(co 2007,2008,2009,2010 Michal Ludvig <http://www.logix.cz/michal>
.br
This is free software.  You may redistribute copies of it under the terms of
the GNU General Public License version 2 <http://www.gnu.org/licenses/gpl.html>.
There is NO WARRANTY, to the extent permitted by law.
";
