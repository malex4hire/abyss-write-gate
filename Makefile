# One command from a clean clone to a published run. No credential, no network,
# no model. `make demo` is the entry point RST-C7 names.

PYTHON ?= python3

.PHONY: demo test verify verify-public clean help

help:
	@echo "make demo    run the adversarial set and publish the register"
	@echo "make test    run the constraint suite"
	@echo "make verify  both"
	@echo "make clean   remove the run directory"
	@echo "make verify-public  check the PUBLISHED surface, anonymously"

demo:
	$(PYTHON) -m gate

test:
	$(PYTHON) -m pytest -q

verify: demo test

# RST-C10/C11/C12. Anonymous, no arguments, no credentials. Re-runnable: the
# published surface can break after the fact.
verify-public:
	$(PYTHON) -m publish

clean:
	rm -rf out
