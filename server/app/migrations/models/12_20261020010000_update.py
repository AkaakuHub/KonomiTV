from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE "mirakc_reservation_conditions" (
            "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            "program_search_condition" TEXT NOT NULL,
            "record_settings" TEXT NOT NULL
        );
        CREATE TABLE "mirakc_recording_exclusions" (
            "program_id" BIGINT PRIMARY KEY NOT NULL,
            "end_time" TIMESTAMP NOT NULL
        );
        CREATE INDEX "idx_mirakc_exclusion_end" ON "mirakc_recording_exclusions" ("end_time");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE "mirakc_recording_exclusions";
        DROP TABLE "mirakc_reservation_conditions";
    """
