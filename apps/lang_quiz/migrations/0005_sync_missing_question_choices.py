from django.db import migrations, models


def add_choices_column_if_missing(apps, schema_editor):
    model = apps.get_model('lang_quiz', 'MissingLanguageQuestion')
    table = model._meta.db_table
    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(cursor, table)
        }
    if 'choices' in columns:
        return

    field = models.JSONField(default=list)
    field.set_attributes_from_name('choices')
    field.model = model
    schema_editor.add_field(model, field)


def remove_choices_column_if_present(apps, schema_editor):
    model = apps.get_model('lang_quiz', 'MissingLanguageQuestion')
    table = model._meta.db_table
    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(cursor, table)
        }
    if 'choices' not in columns:
        return

    field = models.JSONField(default=list)
    field.set_attributes_from_name('choices')
    field.model = model
    schema_editor.remove_field(model, field)


class Migration(migrations.Migration):
    dependencies = [
        ('lang_quiz', '0004_languagequestion_title_ja'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    add_choices_column_if_missing,
                    remove_choices_column_if_present,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='missinglanguagequestion',
                    name='choices',
                    field=models.JSONField(default=list),
                ),
            ],
        ),
    ]
