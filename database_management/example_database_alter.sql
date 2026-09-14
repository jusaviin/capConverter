BEGIN;

ALTER TABLE contracts
ADD CONSTRAINT contracts_unique_signing UNIQUE (player_id, signing_date);

COMMIT;
