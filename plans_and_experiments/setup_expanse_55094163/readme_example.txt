
[notice] A new release of pip is available: 24.0 -> 26.2.1
[notice] To update, run: python -m pip install --upgrade pip
adaptiseq         0.1.11
aioftp            0.28.3
aiohttp           3.14.5
numpy             2.4.6
adaptiSeq 0.1.11
--- CLI: adaptiseq -i accessions.txt -g
[32mNote[0m: batch downloading 3 file(s) across 3 accession(s) with up to 3 worker(s) (configured max 20) (adaptive concurrency)
[32mNote[0m: Transport for ftp.sra.ebi.ac.uk: HTTPS mirror is range-capable; segmented HTTPS
[32mNote[0m: Transport for ftp.sra.ebi.ac.uk: HTTPS mirror is range-capable; segmented HTTPS
[32mNote[0m: Transport for ftp.sra.ebi.ac.uk: HTTPS mirror is range-capable; segmented HTTPS
[32mNote[0m: SRR22904390.metadata.tsv exists, skip downloading metadata for SRR22904390
      SRR22904390.fastq.gz 0.00G 	 
[32mNote[0m: Above Run will be downloaded. You can see the details in SRR22904390.metadata.tsv
[92mSRR22904390 download and md5 check successful, save SRR22904390 in success.log[0m
=======================SRR22904390 download finished=======================
[32mNote[0m: SRR22904370.metadata.tsv exists, skip downloading metadata for SRR22904370
      SRR22904370.fastq.gz 0.00G 	 
[32mNote[0m: Above Run will be downloaded. You can see the details in SRR22904370.metadata.tsv
[92mSRR22904370 download and md5 check successful, save SRR22904370 in success.log[0m
=======================SRR22904370 download finished=======================
[32mNote[0m: SRR22904387.metadata.tsv exists, skip downloading metadata for SRR22904387
      SRR22904387.fastq.gz 0.00G 	 
[32mNote[0m: Above Run will be downloaded. You can see the details in SRR22904387.metadata.tsv
[92mSRR22904387 download and md5 check successful, save SRR22904387 in success.log[0m
=======================SRR22904387 download finished=======================
cli exit: 0
cli verify: runs_complete=3 runs_partial=0 runs_expected=3 files_verified=3 files_expected=3 bytes_verified=47948 bytes_expected=47948 bytes_on_disk=47948 files_on_disk=3 extra_files=0 format=gz runs_complete_3file=0 runs_expected_3file=0 runs_present_unverified=0
--- Python API
get_metadata: 1 row(s); resolve: ['https://sra-pub-run-odp.s3.amazonaws.com/sra/SRR22904390/SRR22904390']
fetch: ['SRR22904390', 'SRR22904370', 'SRR22904387'] [] False
api exit: 0
api verify: runs_complete=3 runs_partial=0 runs_expected=3 files_verified=3 files_expected=3 bytes_verified=47948 bytes_expected=47948 bytes_on_disk=47948 files_on_disk=3 extra_files=0 format=gz runs_complete_3file=0 runs_expected_3file=0 runs_present_unverified=0
