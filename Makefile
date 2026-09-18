# mosaic-demo-small — a small, self-contained Mosaic demo (Donor/Sample/Workflow/Dataset)
#
# ~3,600 realistic synthetic records across 4 entity classes, sized to seriously
# exercise Aperture's faceting, search, and relationship traversal without the
# 90-table sprawl of the hippo-benchmark/brainbank demo.
#
#   make generate   # build data/bundle.yaml via linkml-data-gen (Python API)
#   make migrate    # create/refresh data/mosaic.db's schema (fresh db each time)
#   make ingest     # load data/bundle.yaml into data/mosaic.db
#   make metadata   # regenerate + load the schema's self-description (needs a server)
#   make check-metadata  # fail if that description has drifted from the schema
#   make query      # explore the loaded store via the Mosaic SDK directly
#   make test       # schema-only validation (no built store required)
#   make clean      # wipe data/

DB := data/mosaic.db

.PHONY: generate migrate ingest metadata check-metadata query test clean

generate:
	python3 generate.py

migrate:
	rm -f $(DB) $(DB)-shm $(DB)-wal
	mkdir -p data
	: > $(DB)
	mosaic migrate --schema-dir schemas --db-path $(DB)
	mosaic recipe import recipes/schema-metadata --db-path $(DB)
	mosaic migrate --schema-dir schemas --db-path $(DB)

ingest:
	mosaic ingest --file data/bundle.yaml --db-path $(DB) --validate-schema schemas

## Regenerate the schema's self-description and load it. Needs a running
## server: the rows are read from what Mosaic actually serves, not from the
## schema file, because a file edited but not migrated is exactly the drift
## this guards against.
metadata:
	python3 recipes/schema-metadata/generate_schema_metadata.py -o data/schema_metadata.yaml
	mosaic ingest --file data/schema_metadata.yaml --db-path $(DB) --validate-schema schemas

## Fail if the stored description no longer matches the live schema, or if the
## runtime has grown a slot attribute the recipe does not carry. Regenerating
## during migrate only helps if migrate is run; this is what makes a skipped
## run loud instead of silent.
check-metadata:
	python3 recipes/schema-metadata/generate_schema_metadata.py --check

query:
	python3 query_demo.py --db $(DB)

test:
	mosaic validate --schema schemas/demo.yaml

clean:
	rm -f $(DB) $(DB)-shm $(DB)-wal data/bundle.yaml
