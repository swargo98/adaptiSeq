#!/usr/bin/env perl
# Remove carriage-return progress-bar redraws from a tool's log, keep the text.
#
#   perl strip_progress.pl < raw.log > clean.log
#
# axel (iSeq -p N) redraws its bar with "\r" and no newline, and with no
# terminal the bar is very wide: one 3r arm wrote a 26 GB log. Records are split
# on "\r" (never on "\n", so a bar is never held as one giant line); an axel
# bar ("[ 9%] [....] [2.1MB/s] [00:00]") at the start of a record is dropped up
# to the end of its line, everything else is printed with the "\r" turned into
# a newline. A last line reports how many redraws were removed.
use strict;
use warnings;

$/ = "\r";
my $dropped = 0;
while (my $rec = <STDIN>) {
    chomp $rec;               # strips the trailing "\r" ($/)
    $rec =~ s/\e\[2K//g;      # "erase line" escapes that come with the redraws
    # a bar runs to the end of its line; text after a newline in the same
    # record (e.g. "Downloaded ... Megabyte(s)") is kept
    $dropped++ if $rec =~ s/^\[\s*\d+%\][^\n]*(?:\n|\z)//;
    next if $rec eq '';
    print $rec;
    print "\n" unless $rec =~ /\n\z/;
}
print "[strip_progress: removed $dropped progress-bar redraws]\n" if $dropped;
