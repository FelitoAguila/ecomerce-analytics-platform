.PHONY: up down db-init db-shell simulator

up:
	docker compose up -d

down:
	docker compose down

db-init:
	docker compose run --rm seed

db-shell:
	docker exec -it ecommerce_oltp psql \
		-U $$(sed -n 's/^POSTGRES_USER=//p' .env | tr -d '\r' | xargs) \
		-d $$(sed -n 's/^POSTGRES_DB=//p' .env | tr -d '\r' | xargs)

simulator:
	docker compose run --rm simulator
