from .models import Audit


def audit(db, user, action, entity, entity_id):
    db.add(
        Audit(
            actor=user.id if user else "system",
            role=user.role if user else "SYSTEM",
            action=action,
            entity=entity,
            entity_id=entity_id,
        )
    )
