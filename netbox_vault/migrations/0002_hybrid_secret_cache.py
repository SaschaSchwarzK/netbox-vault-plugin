from django.db import migrations, models



def migrate_cached_secret_presence(apps, schema_editor):
    VaultSecret = apps.get_model('netbox_vault', 'VaultSecret')
    for secret in VaultSecret.objects.all().only('id', 'encrypted_value', 'cache_present'):
        if secret.encrypted_value:
            secret.cache_present = True
            secret.encrypted_value = ''
            secret.save(update_fields=['cache_present', 'encrypted_value', 'last_updated'])


class Migration(migrations.Migration):
    dependencies = [
        ('netbox_vault', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='vaultsecret',
            name='cache_present',
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.RunPython(migrate_cached_secret_presence, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='vaultsecret',
            name='encrypted_value',
        ),
    ]
