# mosaic-demo-small — a small, self-contained Mosaic demo (Donor/Sample/Workflow/Dataset)
#
# ~3,600 realistic synthetic records across 4 entity classes, sized to seriously
# exercise Aperture's faceting, search, and relationship traversal without the
# 90-table sprawl of the hippo-benchmark/brainbank demo.
#
#   make generate   # build data/bundle.yaml via linkml-data-gen (Python API)
#   make migrate    # create/refresh data/mosaic.db's schema (fresh db each time)
#   make ingest     # load data/bundle.yaml into data/mosaic.db
#   make query      # explore the loaded store via the Mosaic SDK directly
#   make test       # schema-only validation (no built store required)
#   make clean      # wipe data/

DB := data/mosaic.db

.PHONY: generate migrate ingest query test clean

generate:
	python3 generate.py

migrate:
	rm -f $(DB) $(DB)-shm $(DB)-wal
	mkdir -p data
	: > $(DB)
	mosaic migrate --schema-dir schemas --db-path $(DB)

ingest:
	mosaic ingest --file data/bundle.yaml --db-path $(DB) --validate-schema schemas/demo.yaml

query:
	python3 query_demo.py --db $(DB)

test:
	mosaic validate --schema schemas/demo.yaml

clean:
	rm -f $(DB) $(DB)-shm $(DB)-wal data/bundle.yaml
