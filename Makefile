# Tests run in Docker so nothing (not even a replayed `rm -rf` incident) can touch the host.
.PHONY: test test-engine test-backend incidents
test: test-engine test-backend incidents
test-engine:
	docker compose -f docker-compose.test.yml run --rm --build engine-tests
test-backend:
	docker compose -f docker-compose.test.yml run --rm --build backend-tests
incidents:
	docker compose -f docker-compose.test.yml run --rm --build incident-replay
