from uuid import uuid4
from sqlalchemy import (
    Column,
    String,
    ForeignKey,
    Integer,
    Float,
    Boolean,
    JSON,
    Text,
    UniqueConstraint,
    CheckConstraint,
    Numeric,
)
from sqlalchemy.orm import relationship
from .database import Base, UTCDateTime, now


def uid():
    return str(uuid4())


def pk():
    return Column(String(64), primary_key=True, default=uid)


def fk(table, **kw):
    return Column(String(64), ForeignKey(table + ".id"), nullable=False, **kw)


class User(Base):
    __tablename__ = "users"
    id = pk()
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String(30), nullable=False)
    display_name = Column(String(120), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    token_version = Column(Integer, default=1, nullable=False)
    __table_args__ = (
        CheckConstraint("role IN ('BEEKEEPER','KVIC_ADMIN','LAB_OPERATOR')"),
    )


class Jurisdiction(Base):
    __tablename__ = "jurisdictions"
    id = pk()
    state = Column(String(8), nullable=False)
    district = Column(String(12), nullable=False)
    name = Column(String(100), nullable=False)
    __table_args__ = (UniqueConstraint("state", "district"),)


class Officer(Base):
    __tablename__ = "kvic_officers"
    id = pk()
    user_id = fk("users", unique=True)
    jurisdiction_id = fk("jurisdictions")


class Beekeeper(Base):
    __tablename__ = "beekeepers"
    id = pk()
    user_id = fk("users", unique=True)
    registered = Column(Boolean, default=True, nullable=False)
    user = relationship(User)


class Lab(Base):
    __tablename__ = "labs"
    id = pk()
    name = Column(String(150), nullable=False)
    active = Column(Boolean, default=True, nullable=False)


class LabOperator(Base):
    __tablename__ = "lab_operators"
    id = pk()
    user_id = fk("users", unique=True)
    lab_id = fk("labs")


class Apiary(Base):
    __tablename__ = "apiaries"
    id = pk()
    beekeeper_id = fk("beekeepers")
    jurisdiction_id = fk("jurisdictions")
    name = Column(String(120), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    beekeeper = relationship(Beekeeper)
    jurisdiction = relationship(Jurisdiction)


class Hive(Base):
    __tablename__ = "hives"
    id = pk()
    apiary_id = fk("apiaries")
    baseline_kg = Column(Float, default=32, nullable=False)
    harvest_target_kg = Column(Float, default=40, nullable=False)
    apiary = relationship(Apiary)


class Device(Base):
    __tablename__ = "devices"
    id = pk()
    hive_id = fk("hives", unique=True)
    key_hash = Column(String(64), nullable=False)
    source_type = Column(String(30), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    last_contact = Column(UTCDateTime)
    hive = relationship(Hive)
    __table_args__ = (
        CheckConstraint("source_type IN ('SIMULATOR','PHYSICAL_DEVICE')"),
    )


class Telemetry(Base):
    __tablename__ = "telemetry"
    id = pk()
    device_id = fk("devices")
    measured_at = Column(UTCDateTime, nullable=False, index=True)
    received_at = Column(UTCDateTime, default=now, nullable=False)
    weight_kg = Column(Float, nullable=False)
    temperature_c = Column(Float, nullable=False)
    humidity_percent = Column(Float, nullable=False)
    __table_args__ = (
        UniqueConstraint("device_id", "measured_at"),
        CheckConstraint("weight_kg >= 0 AND weight_kg <= 200"),
        CheckConstraint("temperature_c >= -40 AND temperature_c <= 80"),
        CheckConstraint("humidity_percent >= 0 AND humidity_percent <= 100"),
    )


class Alert(Base):
    __tablename__ = "alerts"
    id = pk()
    hive_id = fk("hives")
    type = Column(String(60), nullable=False)
    severity = Column(String(20), nullable=False)
    evidence = Column(JSON, nullable=False)
    recommendation = Column(Text, nullable=False)
    opened_at = Column(UTCDateTime, nullable=False)
    last_seen = Column(UTCDateTime, nullable=False)
    resolved_at = Column(UTCDateTime)


class RegionalAlert(Base):
    __tablename__ = "regional_alerts"
    id = pk()
    jurisdiction_id = fk("jurisdictions")
    evidence = Column(JSON, nullable=False)
    opened_at = Column(UTCDateTime, default=now)
    last_seen = Column(UTCDateTime, default=now)
    resolved_at = Column(UTCDateTime)


class Extraction(Base):
    __tablename__ = "extractions"
    id = pk()
    beekeeper_id = fk("beekeepers")
    apiary_id = fk("apiaries")
    extracted_at = Column(UTCDateTime, nullable=False)
    quantity_kg = Column(Numeric(10, 3), nullable=False)
    honey_type = Column(String(120))
    __table_args__ = (CheckConstraint("quantity_kg > 0"),)


class ExtractionHive(Base):
    __tablename__ = "extraction_hives"
    id = pk()
    extraction_id = fk("extractions")
    hive_id = fk("hives")
    __table_args__ = (UniqueConstraint("extraction_id", "hive_id"),)


class Maintenance(Base):
    __tablename__ = "maintenance_events"
    id = pk()
    hive_id = fk("hives")
    user_id = fk("users")
    occurred_at = Column(UTCDateTime, nullable=False)
    description = Column(String(300), nullable=False)


class Batch(Base):
    __tablename__ = "batches"
    id = pk()
    extraction_id = fk("extractions", unique=True)
    state = Column(String(40), default="PENDING_LAB", nullable=False)
    version = Column(Integer, default=1, nullable=False)
    extraction = relationship(Extraction)
    __table_args__ = (
        CheckConstraint(
            "state IN ('PENDING_LAB','PENDING_KVIC_REVIEW','REJECTED','PUBLICLY_VERIFIABLE')"
        ),
    )


class LabAssignment(Base):
    __tablename__ = "lab_assignments"
    id = pk()
    batch_id = fk("batches", unique=True)
    lab_id = fk("labs")
    officer_id = fk("kvic_officers")
    assigned_at = Column(UTCDateTime, default=now, nullable=False)


class LabResult(Base):
    __tablename__ = "lab_results"
    id = pk()
    batch_id = fk("batches")
    lab_id = fk("labs")
    submitted_by = fk("users")
    laboratory_name = Column(String(150), nullable=False)
    report_reference = Column(String(150), nullable=False)
    tested_at = Column(UTCDateTime, nullable=False)
    entered_at = Column(UTCDateTime, default=now, nullable=False)
    parameters = Column(JSON, nullable=False)
    outcome = Column(String(20), nullable=False)
    evidence_reference = Column(String(500), nullable=False)
    report_content = Column(Text)
    report_sha256 = Column(String(64))
    version = Column(Integer, nullable=False)
    supersedes_id = Column(String(64), ForeignKey("lab_results.id"))
    finalized_at = Column(UTCDateTime)
    finalized_hash = Column(String(64))
    __table_args__ = (
        UniqueConstraint("batch_id", "version"),
        CheckConstraint("outcome IN ('PASS','FAIL','INCONCLUSIVE')"),
    )


class Review(Base):
    __tablename__ = "batch_reviews"
    id = pk()
    batch_id = fk("batches", unique=True)
    officer_id = fk("kvic_officers")
    result_id = Column(String(64), ForeignKey("lab_results.id"))
    decision = Column(String(20), nullable=False)
    reason = Column(Text, nullable=False)
    timestamp = Column(UTCDateTime, default=now, nullable=False)


class BatchEvent(Base):
    __tablename__ = "batch_events"
    id = pk()
    batch_id = fk("batches")
    event = Column(String(50), nullable=False)
    timestamp = Column(UTCDateTime, default=now, nullable=False)


class Release(Base):
    __tablename__ = "batch_release"
    id = pk()
    batch_id = fk("batches", unique=True)
    snapshot = Column(JSON, nullable=False)
    snapshot_hash = Column(String(64), nullable=False)
    created_at = Column(UTCDateTime, default=now, nullable=False)


class LedgerBlock(Base):
    __tablename__ = "ledger_blocks"
    id = pk()
    block_number = Column(Integer, unique=True, nullable=False)
    batch_id = fk("batches", unique=True)
    previous_hash = Column(String(64), nullable=False)
    current_hash = Column(String(64), nullable=False)
    canonical_record = Column(JSON, nullable=False)


class LedgerHead(Base):
    __tablename__ = "ledger_head"
    id = Column(Integer, primary_key=True)
    version = Column(Integer, default=0, nullable=False)


class SyncRecord(Base):
    __tablename__ = "offline_sync_records"
    id = pk()
    user_id = fk("users")
    operation_id = Column(String(64), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    batch_id = fk("batches")
    __table_args__ = (UniqueConstraint("user_id", "operation_id"),)


class Audit(Base):
    __tablename__ = "audit_logs"
    id = pk()
    actor = Column(String(80), nullable=False)
    role = Column(String(30), nullable=False)
    action = Column(String(60), nullable=False)
    entity = Column(String(40), nullable=False)
    entity_id = Column(String(80), nullable=False)
    timestamp = Column(UTCDateTime, default=now, nullable=False)

class DemoAccount(Base):
    __tablename__ = 'demo_accounts'
    username = Column(String(80), primary_key=True)
    user_id = fk('users')
    password_hash = Column(Text, nullable=False)
