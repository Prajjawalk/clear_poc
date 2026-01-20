# Generated manually for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('data_pipeline', '0005_alter_variable_created_at_alter_variable_updated_at'),
    ]

    operations = [
        # Composite index for checking existing records
        migrations.AddIndex(
            model_name='variabledata',
            index=models.Index(fields=['variable', 'start_date', 'gid'], name='vardata_var_date_gid_idx'),
        ),
        
        # Index for filtering by variable
        migrations.AddIndex(
            model_name='variabledata',
            index=models.Index(fields=['variable', 'start_date'], name='vardata_var_date_idx'),
        ),
        
        # Index for location-based queries
        migrations.AddIndex(
            model_name='variabledata',
            index=models.Index(fields=['gid', 'start_date'], name='vardata_gid_date_idx'),
        ),
    ]