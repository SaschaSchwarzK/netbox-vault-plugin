from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

backend_item = PluginMenuItem(
    link="plugins:netbox_vault:vaultbackend_list",
    link_text="Vault Backends",
    permissions=["netbox_vault.view_vaultbackend"],
    buttons=(
        PluginMenuButton(
            link="plugins:netbox_vault:vaultbackend_add",
            title="Add vault backend",
            icon_class="mdi mdi-plus-thick",
            permissions=["netbox_vault.add_vaultbackend"],
        ),
    ),
)

secret_item = PluginMenuItem(
    link="plugins:netbox_vault:vaultsecret_list",
    link_text="Vault Secrets",
    permissions=["netbox_vault.view_vaultsecret"],
    buttons=(
        PluginMenuButton(
            link="plugins:netbox_vault:vaultsecret_add",
            title="Add vault secret",
            icon_class="mdi mdi-plus-thick",
            permissions=["netbox_vault.add_vaultsecret"],
        ),
        PluginMenuButton(
            link="plugins:netbox_vault:vaultsecret_refresh_all",
            title="Refresh all cached secrets",
            icon_class="mdi mdi-refresh",
            permissions=["netbox_vault.change_vaultsecret"],
        ),
    ),
)

menu = PluginMenu(
    label="Vault",
    groups=(
        ("Vault", (backend_item, secret_item)),
    ),
    icon_class="mdi mdi-vault",
)
