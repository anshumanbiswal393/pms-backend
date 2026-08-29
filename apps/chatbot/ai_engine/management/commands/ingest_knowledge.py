import os
from django.core.management.base import BaseCommand
from apps.chatbot.ai_engine.services import IngestionService


class Command(BaseCommand):
    help = 'Ingests SRS Specification document and Website Navigation Routes using IngestionService.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting Knowledge Base Ingestion..."))

        # 1. Ingest SRS Document
        doc_path = os.getenv("SRS_DOC_PATH", "Software Requirements Specification (SRS)-PMS_Retrod - Anushka (1).docx")
        if os.path.exists(doc_path):
            srs_count = IngestionService.ingest_docx_file(doc_path)
            self.stdout.write(self.style.SUCCESS(f"Successfully ingested {srs_count} SRS Document chunks."))
        else:
            self.stdout.write(self.style.WARNING(f"SRS Document '{doc_path}' not found."))

        # 2. Ingest Website Routes
        route_count = IngestionService.ingest_routes()
        self.stdout.write(self.style.SUCCESS(f"Successfully ingested {route_count} Website Navigation Routes with pgvector embeddings."))
        self.stdout.write(self.style.SUCCESS("All Knowledge Base Ingestion Completed!"))

