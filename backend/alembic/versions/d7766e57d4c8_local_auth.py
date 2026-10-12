# ruff: noqa: E501
"""Additive local-auth schema; generated SQL is retained verbatim for both dialects."""

from alembic import op

revision = "d7766e57d4c8"
down_revision = "0040_hierarchical_forecast"
branch_labels = None
depends_on = None


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    op.execute(
        "\nCREATE TABLE auth_account (\n\taccount_id VARCHAR(36) NOT NULL, \n\tprincipal_id VARCHAR(36) NOT NULL, \n\tusername_normalized VARCHAR(64) NOT NULL, \n\tpassword_hash TEXT NOT NULL, \n\trole VARCHAR(20) NOT NULL, \n\tstatus VARCHAR(10) NOT NULL, \n\tmust_change_password BOOLEAN NOT NULL, \n\tauth_revision INTEGER NOT NULL, \n\tgrant_revision INTEGER NOT NULL, \n\tmanaged_organization_ids JSONB NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tdisabled_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (account_id), \n\tCONSTRAINT ck_auth_role CHECK (role IN ('ADMIN','BUSINESS_USER')), \n\tCONSTRAINT ck_auth_status CHECK (status IN ('ACTIVE','DISABLED')), \n\tCONSTRAINT ck_auth_revision CHECK (auth_revision > 0 AND grant_revision > 0), \n\tUNIQUE (principal_id), \n\tUNIQUE (username_normalized)\n)\n\n"
        if postgres
        else "\nCREATE TABLE auth_account (\n\taccount_id VARCHAR(36) NOT NULL, \n\tprincipal_id VARCHAR(36) NOT NULL, \n\tusername_normalized VARCHAR(64) NOT NULL, \n\tpassword_hash TEXT NOT NULL, \n\trole VARCHAR(20) NOT NULL, \n\tstatus VARCHAR(10) NOT NULL, \n\tmust_change_password BOOLEAN NOT NULL, \n\tauth_revision INTEGER NOT NULL, \n\tgrant_revision INTEGER NOT NULL, \n\tmanaged_organization_ids JSON NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tdisabled_at DATETIME, \n\tPRIMARY KEY (account_id), \n\tCONSTRAINT ck_auth_role CHECK (role IN ('ADMIN','BUSINESS_USER')), \n\tCONSTRAINT ck_auth_status CHECK (status IN ('ACTIVE','DISABLED')), \n\tCONSTRAINT ck_auth_revision CHECK (auth_revision > 0 AND grant_revision > 0), \n\tUNIQUE (principal_id), \n\tUNIQUE (username_normalized)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE auth_session (\n\tsession_id VARCHAR(36) NOT NULL, \n\ttoken_digest VARCHAR(64) NOT NULL, \n\tkind VARCHAR(10) NOT NULL, \n\taccount_id VARCHAR(36), \n\tcsrf_token_digest VARCHAR(64) NOT NULL, \n\tissued_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tlast_seen_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tidle_expires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tabsolute_expires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tauth_revision INTEGER, \n\tgrant_revision INTEGER, \n\trevoked_at TIMESTAMP WITH TIME ZONE, \n\trevoke_reason VARCHAR(64), \n\tPRIMARY KEY (session_id), \n\tCONSTRAINT ck_auth_session_kind CHECK ((kind='PREAUTH' AND account_id IS NULL AND auth_revision IS NULL AND grant_revision IS NULL) OR (kind='END_USER' AND account_id IS NOT NULL AND auth_revision > 0 AND grant_revision > 0)), \n\tCONSTRAINT ck_auth_session_expiry CHECK (absolute_expires_at > issued_at), \n\tUNIQUE (token_digest), \n\tFOREIGN KEY(account_id) REFERENCES auth_account (account_id) ON DELETE RESTRICT\n)\n\n"
        if postgres
        else "\nCREATE TABLE auth_session (\n\tsession_id VARCHAR(36) NOT NULL, \n\ttoken_digest VARCHAR(64) NOT NULL, \n\tkind VARCHAR(10) NOT NULL, \n\taccount_id VARCHAR(36), \n\tcsrf_token_digest VARCHAR(64) NOT NULL, \n\tissued_at DATETIME NOT NULL, \n\tlast_seen_at DATETIME NOT NULL, \n\tidle_expires_at DATETIME NOT NULL, \n\tabsolute_expires_at DATETIME NOT NULL, \n\tauth_revision INTEGER, \n\tgrant_revision INTEGER, \n\trevoked_at DATETIME, \n\trevoke_reason VARCHAR(64), \n\tPRIMARY KEY (session_id), \n\tCONSTRAINT ck_auth_session_kind CHECK ((kind='PREAUTH' AND account_id IS NULL AND auth_revision IS NULL AND grant_revision IS NULL) OR (kind='END_USER' AND account_id IS NOT NULL AND auth_revision > 0 AND grant_revision > 0)), \n\tCONSTRAINT ck_auth_session_expiry CHECK (absolute_expires_at > issued_at), \n\tUNIQUE (token_digest), \n\tFOREIGN KEY(account_id) REFERENCES auth_account (account_id) ON DELETE RESTRICT\n)\n\n"
    )
    op.execute("CREATE INDEX ix_auth_session_account ON auth_session (account_id, revoked_at)")
    op.execute(
        "\nCREATE TABLE auth_resource_grant (\n\tgrant_id VARCHAR(36) NOT NULL, \n\tprincipal_id VARCHAR(36) NOT NULL, \n\tresource_kind VARCHAR(10) NOT NULL, \n\tcapability VARCHAR(40) NOT NULL, \n\torganization_id VARCHAR(200) NOT NULL, \n\tapproved_by_principal VARCHAR(36) NOT NULL, \n\tapproval_reference VARCHAR(200) NOT NULL, \n\treason VARCHAR(500) NOT NULL, \n\tgrant_revision INTEGER NOT NULL, \n\tforecast_binding JSONB, \n\tquality_binding JSONB, \n\tvalid_from TIMESTAMP WITH TIME ZONE NOT NULL, \n\tvalid_until TIMESTAMP WITH TIME ZONE NOT NULL, \n\trevoked_at TIMESTAMP WITH TIME ZONE, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (grant_id), \n\tCONSTRAINT ck_auth_grant_expiry CHECK (valid_until > valid_from), \n\tCONSTRAINT ck_auth_grant_revision CHECK (grant_revision > 0), \n\tCONSTRAINT ck_auth_grant_binding CHECK ((resource_kind='FORECAST' AND capability='may_read_forecast' AND forecast_binding IS NOT NULL AND quality_binding IS NULL) OR (resource_kind='QUALITY' AND capability='may_read_quality' AND quality_binding IS NOT NULL AND forecast_binding IS NULL)), \n\tFOREIGN KEY(principal_id) REFERENCES auth_account (principal_id) ON DELETE RESTRICT\n)\n\n"
        if postgres
        else "\nCREATE TABLE auth_resource_grant (\n\tgrant_id VARCHAR(36) NOT NULL, \n\tprincipal_id VARCHAR(36) NOT NULL, \n\tresource_kind VARCHAR(10) NOT NULL, \n\tcapability VARCHAR(40) NOT NULL, \n\torganization_id VARCHAR(200) NOT NULL, \n\tapproved_by_principal VARCHAR(36) NOT NULL, \n\tapproval_reference VARCHAR(200) NOT NULL, \n\treason VARCHAR(500) NOT NULL, \n\tgrant_revision INTEGER NOT NULL, \n\tforecast_binding JSON, \n\tquality_binding JSON, \n\tvalid_from DATETIME NOT NULL, \n\tvalid_until DATETIME NOT NULL, \n\trevoked_at DATETIME, \n\tcreated_at DATETIME NOT NULL, \n\tPRIMARY KEY (grant_id), \n\tCONSTRAINT ck_auth_grant_expiry CHECK (valid_until > valid_from), \n\tCONSTRAINT ck_auth_grant_revision CHECK (grant_revision > 0), \n\tCONSTRAINT ck_auth_grant_binding CHECK ((resource_kind='FORECAST' AND capability='may_read_forecast' AND forecast_binding IS NOT NULL AND quality_binding IS NULL) OR (resource_kind='QUALITY' AND capability='may_read_quality' AND quality_binding IS NOT NULL AND forecast_binding IS NULL)), \n\tFOREIGN KEY(principal_id) REFERENCES auth_account (principal_id) ON DELETE RESTRICT\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_auth_grant_principal ON auth_resource_grant (principal_id, capability, revoked_at)"
    )
    op.execute(
        "\nCREATE TABLE auth_audit_event (\n\tevent_id VARCHAR(36) NOT NULL, \n\toccurred_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tactor_principal_id VARCHAR(36), \n\ttarget_account_id VARCHAR(36), \n\ttarget_grant_id VARCHAR(36), \n\taction VARCHAR(64) NOT NULL, \n\tresult_code VARCHAR(64) NOT NULL, \n\trevision_before INTEGER, \n\trevision_after INTEGER, \n\tcorrelation_id VARCHAR(36) NOT NULL, \n\torganization_id VARCHAR(200), \n\tlogin_bucket_digest VARCHAR(64), \n\treason_code VARCHAR(64) NOT NULL, \n\tPRIMARY KEY (event_id)\n)\n\n"
        if postgres
        else "\nCREATE TABLE auth_audit_event (\n\tevent_id VARCHAR(36) NOT NULL, \n\toccurred_at DATETIME NOT NULL, \n\tactor_principal_id VARCHAR(36), \n\ttarget_account_id VARCHAR(36), \n\ttarget_grant_id VARCHAR(36), \n\taction VARCHAR(64) NOT NULL, \n\tresult_code VARCHAR(64) NOT NULL, \n\trevision_before INTEGER, \n\trevision_after INTEGER, \n\tcorrelation_id VARCHAR(36) NOT NULL, \n\torganization_id VARCHAR(200), \n\tlogin_bucket_digest VARCHAR(64), \n\treason_code VARCHAR(64) NOT NULL, \n\tPRIMARY KEY (event_id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_auth_audit_bucket ON auth_audit_event (login_bucket_digest, occurred_at)"
    )
    op.execute(
        "CREATE INDEX ix_auth_audit_org_time ON auth_audit_event (organization_id, occurred_at)"
    )
    if postgres:
        for table, columns in (
            ("auth_account", ("auth_revision", "grant_revision")),
            ("auth_session", ("auth_revision", "grant_revision")),
            ("auth_resource_grant", ("grant_revision",)),
            ("auth_audit_event", ("revision_before", "revision_after")),
        ):
            for column in columns:
                op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE BIGINT")
        op.execute("""
            CREATE FUNCTION local_auth_immutable_identity() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Account identity cannot be deleted';
              END IF;
              IF NEW.account_id IS DISTINCT FROM OLD.account_id
                 OR NEW.principal_id IS DISTINCT FROM OLD.principal_id THEN
                RAISE EXCEPTION 'Account identity is immutable';
              END IF;
              IF NEW.auth_revision < OLD.auth_revision
                 OR NEW.grant_revision < OLD.grant_revision THEN
                RAISE EXCEPTION 'Revision cannot decrease';
              END IF;
              RETURN NEW;
            END $$
        """)
        op.execute("""
            CREATE TRIGGER auth_account_identity_guard BEFORE UPDATE OR DELETE
            ON auth_account FOR EACH ROW EXECUTE FUNCTION local_auth_immutable_identity()
        """)
        op.execute("""
            CREATE FUNCTION local_auth_audit_append_only() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
              RAISE EXCEPTION 'Authentication audit is append only';
            END $$
        """)
        op.execute("""
            CREATE TRIGGER auth_audit_append_only BEFORE UPDATE OR DELETE
            ON auth_audit_event FOR EACH ROW EXECUTE FUNCTION local_auth_audit_append_only()
        """)
        op.execute("""
            ALTER TABLE auth_resource_grant ADD CONSTRAINT ck_auth_exact_binding CHECK (COALESCE((
              organization_id <> '' AND position('*' in organization_id) = 0 AND
              CASE WHEN resource_kind = 'FORECAST' THEN
                jsonb_typeof(forecast_binding) = 'object' AND
                forecast_binding ?& ARRAY['identity','expected_source_result_hash','source_authority_version'] AND
                jsonb_typeof(forecast_binding->'identity') = 'object' AND
                (forecast_binding->'identity') ?& ARRAY['source_kind','forecast_family','run_id','hierarchy_level','entity_id','target_season','origin_date','baseline_id','policy_version'] AND
                (forecast_binding->>'expected_source_result_hash') ~ '^[0-9a-f]{64}$' AND
                position('*' in forecast_binding::text) = 0
              ELSE
                jsonb_typeof(quality_binding) = 'object' AND
                quality_binding ?& ARRAY['query','source_split','target_season','scope','evidence_policy_version','evidence_hashes','evidence_set_digest'] AND
                (quality_binding->>'evidence_set_digest') ~ '^[0-9a-f]{64}$' AND
                position('*' in quality_binding::text) = 0
              END
            ), FALSE))
        """)


def downgrade() -> None:
    op.drop_table("auth_audit_event")
    op.drop_table("auth_resource_grant")
    op.drop_table("auth_session")
    op.drop_table("auth_account")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS local_auth_audit_append_only()")
        op.execute("DROP FUNCTION IF EXISTS local_auth_immutable_identity()")
