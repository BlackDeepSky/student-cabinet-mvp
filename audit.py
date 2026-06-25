"""
Запись действий администратора в журнал аудита.
"""


def write_audit(conn, action: str, entity: str, entity_name: str = None, details: str = None):
    conn.execute(
        "INSERT INTO admin_audit_log (action, entity, entity_name, details) VALUES (%s, %s, %s, %s)",
        (action, entity, entity_name, details)
    )
