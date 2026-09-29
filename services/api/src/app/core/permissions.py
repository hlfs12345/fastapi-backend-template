ROLES_VIEW = "roles.view"
ROLES_MANAGE = "roles.manage"
USERS_VIEW = "users.view"
USERS_MANAGE = "users.manage"
CONTACTS_VIEW = "contacts.view"
CONTACTS_EDIT = "contacts.edit"
CONTACTS_EXPORT = "contacts.export"
CONTACTS_VIEW_SENSITIVE = "contacts.view_sensitive"
CAMPAIGNS_CREATE = "campaigns.create"
CAMPAIGNS_SEND = "campaigns.send"
STOCK_VIEW = "stock.view"
STOCK_ADJUST = "stock.adjust"
TRACKING_VIEW = "tracking.view"
TRACKING_MANAGE = "tracking.manage"

PERMISSION_CATALOG = {
    ROLES_VIEW: "View roles and their permissions.",
    ROLES_MANAGE: "Create and update roles and role assignments.",
    USERS_VIEW: "View tenant users.",
    USERS_MANAGE: "Manage tenant users.",
    CONTACTS_VIEW: "View contacts.",
    CONTACTS_EDIT: "Create and update contacts.",
    CONTACTS_EXPORT: "Export contact data.",
    CONTACTS_VIEW_SENSITIVE: "View sensitive contact data.",
    CAMPAIGNS_CREATE: "Create and update campaigns.",
    CAMPAIGNS_SEND: "Start campaign sends.",
    STOCK_VIEW: "View inventory.",
    STOCK_ADJUST: "Adjust inventory quantities.",
    TRACKING_VIEW: "View tracked assets and positions.",
    TRACKING_MANAGE: "Manage trackers and assignments.",
}

ALL_PERMISSION_CODES = frozenset(PERMISSION_CATALOG)
