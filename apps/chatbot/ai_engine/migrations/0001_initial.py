from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="KnowledgeChunk",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(db_index=True, max_length=255)),
                ("content", models.TextField()),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("staff_assistance", "Staff Assistance"),
                            ("website_navigation", "Website Navigation"),
                            ("pms_workflow", "PMS Workflow"),
                            ("general_faq", "General FAQ"),
                        ],
                        db_index=True,
                        default="pms_workflow",
                        max_length=50,
                    ),
                ),
                (
                    "source_doc",
                    models.CharField(db_index=True, default="SRS-PMS_Retrod", max_length=255),
                ),
                (
                    "embedding",
                    models.JSONField(
                        blank=True,
                        help_text="Stored 384-dim vector embedding list",
                        null=True,
                    ),
                ),
                (
                    "embedding_json",
                    models.JSONField(
                        blank=True,
                        help_text="Stored vector embedding list",
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "chatbot_knowledge_chunk",
            },
        ),
    ]
