# Conda recipe

`meta.yaml` is the bioconda recipe for adaptiSeq. It builds the released PyPI
sdist (not this checkout), installs the external tools the CLI shells out to,
and runs the offline test suite shipped in the sdist as its test step.

## Build and test locally

```bash
conda install -n base conda-build
conda build recipe -c conda-forge -c bioconda
conda create -n adaptiseq -c local -c conda-forge -c bioconda adaptiseq
```

## Submitting to bioconda (one time)

1. Fork <https://github.com/bioconda/bioconda-recipes> and create a branch.
2. Copy this file to `recipes/adaptiseq/meta.yaml` in the fork.
3. Open a pull request. Bioconda CI lints, builds and tests the recipe; once
   it is green, ask for review (comment `@BiocondaBot please add label`).
4. After merge the package is installable with
   `conda install -c conda-forge -c bioconda adaptiseq`.

## Releasing a new version

1. Bump `__version__` in `adaptiseq/__init__.py` and publish to PyPI.
2. Bioconda's autobump bot usually opens the version-bump PR on
   bioconda-recipes within a day. Otherwise update `version` and `sha256`
   there by hand (the sha256 is listed on the PyPI "Download files" page).
3. Mirror the new `version` and `sha256` here, so CI keeps building the
   current release.
4. Reset `build: number` to 0 for a new version; increment it only when the
   recipe changes and the version does not.
