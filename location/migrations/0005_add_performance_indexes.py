# Generated manually for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('location', '0004_alter_gazetteer_created_at_and_more'),
    ]

    operations = [
        # Index for Gazetteer lookups - most critical for IOM processing
        migrations.AddIndex(
            model_name='gazetteer',
            index=models.Index(fields=['source', 'code'], name='gazetteer_source_code_idx'),
        ),
        migrations.AddIndex(
            model_name='gazetteer',
            index=models.Index(fields=['source', 'name'], name='gazetteer_source_name_idx'),
        ),
        migrations.AddIndex(
            model_name='gazetteer',
            index=models.Index(fields=['code'], name='gazetteer_code_idx'),
        ),

        # Index for Location lookups
        migrations.AddIndex(
            model_name='location',
            index=models.Index(fields=['geo_id', 'admin_level'], name='location_geo_id_level_idx'),
        ),
        migrations.AddIndex(
            model_name='location',
            index=models.Index(fields=['geo_id'], name='location_geo_id_idx'),
        ),
        migrations.AddIndex(
            model_name='location',
            index=models.Index(fields=['name', 'admin_level'], name='location_name_level_idx'),
        ),
    ]
