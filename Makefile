.PHONY: up down db-init db-shell

up:
	docker compose up -d

down:
	docker compose down

db-init:
	uv run python src/oltp/seed.py

db-shell:
	docker exec -it ecommerce_oltp psql \
		-U $$(sed -n 's/^POSTGRES_USER=//p' .env | tr -d '\r' | xargs) \
		-d $$(sed -n 's/^POSTGRES_DB=//p' .env | tr -d '\r' | xargs)
