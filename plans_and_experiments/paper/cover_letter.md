# Cover letter (draft)

[[Date]]

Dear Editor,

We submit "adaptiSeq: complete, parallel download of public sequencing accession
lists" for consideration as an Application Note in *Bioinformatics*.

adaptiSeq builds on iSeq (Chao *et al.*, *Bioinformatics*, 2024), which it
reimplements in Python, and we want to be explicit about what is new. First,
adaptiSeq completes accession lists that iSeq does not: on a 241-run public
project it verified [[N]] runs where iSeq verified [[N]], the difference being
runs with three FASTQ files. Second, by resolving and downloading the runs of a
list concurrently, with default settings, it was [[ratio]] times
(95% CI [[lo]] to [[hi]]) as fast as the fastest of iSeq, Kingfisher, and
fastq-dl on that project, measured on two machines with randomised run order and
checksum-verified output. Third, it is an importable library with typed errors,
so pipelines can call it directly instead of wrapping a shell script.

The software is MIT-licensed, installable from PyPI, and archived at
[[Zenodo DOI]]; the benchmark scripts, accession lists, and raw results are
public at [[repository and commit]]. The manuscript has not been published or
submitted elsewhere, and all authors have approved it.

[[Suggested or excluded reviewers, if any. The iSeq authors are the people best
placed to judge the comparison; say so if you are content for them to review.]]

Sincerely,

[[Corresponding author, affiliation, email]]
