-- Skills & Knowledge management schema — Oracle version
-- Run: sqlplus user/pass@db @schema_oracle.sql

-- ============================================================================
-- Contributions
-- ============================================================================
CREATE TABLE contributions (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contribution_type VARCHAR2(20) NOT NULL CHECK (contribution_type IN ('skill', 'knowledge')),
    name            VARCHAR2(200) NOT NULL,
    domain          VARCHAR2(200),
    status          VARCHAR2(20) DEFAULT 'draft' NOT NULL
                    CHECK (status IN ('draft', 'pending_review', 'approved', 'rejected', 'archived')),
    current_version NUMBER DEFAULT 1 NOT NULL,
    created_by      VARCHAR2(200) NOT NULL,
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at      TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    metadata_json   CLOB DEFAULT '{}' CHECK (metadata_json IS JSON),
    tags_json       CLOB DEFAULT '[]' CHECK (tags_json IS JSON),

    CONSTRAINT uq_contribution UNIQUE (contribution_type, name)
);

CREATE INDEX idx_contrib_type ON contributions(contribution_type);
CREATE INDEX idx_contrib_status ON contributions(status);
CREATE INDEX idx_contrib_domain ON contributions(domain);

-- ============================================================================
-- Versions: immutable, append-only
-- ============================================================================
CREATE TABLE contribution_versions (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contribution_id NUMBER NOT NULL REFERENCES contributions(id) ON DELETE CASCADE,
    version         NUMBER NOT NULL,
    content         CLOB NOT NULL,
    frontmatter_json CLOB DEFAULT '{}' CHECK (frontmatter_json IS JSON),
    files_json      CLOB DEFAULT '{}' CHECK (files_json IS JSON),
    content_sha256  VARCHAR2(64) NOT NULL,
    created_by      VARCHAR2(200) NOT NULL,
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    change_summary  VARCHAR2(1000),

    CONSTRAINT uq_version UNIQUE (contribution_id, version)
);

CREATE INDEX idx_ver_contrib ON contribution_versions(contribution_id);

-- Full-text index (Oracle Text)
CREATE INDEX idx_ver_content_ft ON contribution_versions(content)
    INDEXTYPE IS CTXSYS.CONTEXT
    PARAMETERS ('SYNC (ON COMMIT)');

-- ============================================================================
-- Approvals: audit trail
-- ============================================================================
CREATE TABLE approvals (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contribution_id NUMBER NOT NULL REFERENCES contributions(id) ON DELETE CASCADE,
    version         NUMBER NOT NULL,
    decision        VARCHAR2(20) NOT NULL CHECK (decision IN ('approved', 'rejected')),
    decided_by      VARCHAR2(200) NOT NULL,
    reason          VARCHAR2(2000),
    decided_at      TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE INDEX idx_appr_contrib ON approvals(contribution_id);

-- ============================================================================
-- View: latest approved version
-- ============================================================================
CREATE OR REPLACE VIEW active_contributions AS
SELECT
    c.id,
    c.contribution_type,
    c.name,
    c.domain,
    c.status,
    c.tags_json,
    c.metadata_json,
    c.created_by,
    v.version,
    v.content,
    v.frontmatter_json,
    v.files_json,
    v.content_sha256,
    v.created_at AS version_created_at
FROM contributions c
JOIN contribution_versions v
    ON v.contribution_id = c.id
    AND v.version = c.current_version
WHERE c.status = 'approved';
