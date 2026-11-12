# Conda recipe

`meta.yaml` is the bioconda recipe for adaptiSeq, as accepted into
[bioconda-recipes](https://github.com/bioconda/bioconda-recipes/tree/master/recipes/adaptiseq)
(pull request #71375). It builds the released PyPI sdist (not this checkout), installs the
external tools the CLI shells out to, and runs `--version`, `--help` and `pip check` as its test step.

## Build and test locally

```bash
conda install -n base conda-build
conda build recipe -c conda-forge -c bioconda
conda create -n adaptiseq -c local -c conda-forge -c bioconda adaptiseq
```

## What the recipe pins

`meta.yaml` builds the sdist uploaded to PyPI, so `version` and `sha256` must be those of that
exact file. For 0.1.15 the sdist is `adaptiseq-0.1.15.tar.gz`, sha256
`de80376b7b51b162fbc96d1b8134eae58c21f47ebef0c74f752980c705683842`, uploaded together with the wheel
`adaptiseq-0.1.15-py3-none-any.whl`, sha256 `e204b6825161cba7f46ca06d383599a76f91161c1cdeec2b23e0e2ca9052c694`
(the wheel rebuilds bit for bit with `SOURCE_DATE_EPOCH=1794521893 python -m build` from this source, since it
contains no tests; an sdist does not, so pin the uploaded file). If a different sdist is uploaded, copy the sha256 from the PyPI
"Download files" page, or from `sha256sum dist/adaptiseq-*.tar.gz`, into `meta.yaml` before the bioconda
pull request. The recipe's test step runs `adaptiseq --version`, `adaptiseq --help` and `pip check`. It does not run
pytest: bioconda repeats the test commands in a bare container that has neither pytest nor the `tests/` folder (the
first pull request failed there although conda-build had passed the 273-test suite). To run the suite against a built
package, add `source_files: [tests]`, the pytest command and `requires: pytest` to a local copy of the recipe.

## Submitting to bioconda (one time)

1. Fork <https://github.com/bioconda/bioconda-recipes> and create a branch.
2. Copy this file to `recipes/adaptiseq/meta.yaml` in the fork.
3. Optionally lint it first with `bioconda-utils` (see the bioconda-recipes contributing guide):
   `bioconda-utils lint --packages adaptiseq recipes config.yml`.
4. Open a pull request. Bioconda CI lints, builds and tests the recipe; once
   it is green, ask for review (comment `@BiocondaBot please add label`).
5. After merge the package is installable with
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
