# One command from a clean clone to a published run. No credential, no network,
# no model. `make demo` is the entry point RST-C7 names.

PYTHON ?= python3

.PHONY: demo test verify clean help

help:
	@echo "make demo    run the adversarial set and publish the register"
	@echo "make test    run the constraint suite"
	@echo "make verify  both"
	@echo "make clean   remove the run directory"

demo:
	$(PYTHON) -m gate

test:
	$(PYTHON) -m pytest -q

verify: demo test

clean:
	rm -rf out
