-- Skills & Knowledge management schema
-- Run: psql $DATABASE_URL -f schema.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- for gen_random_uuid if needed
-- CREATE EXTENSION IF NOT EXISTS vector;   -- uncomment when ready for RAG

-- ============================================================================
-- Contributions: both skills and knowledge in one table
-- ============================================================================
CREATE TABLE IF NOT EXISTS contributions (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    type            TEXT NOT NULL CHECK (type IN ('skill', 'knowledge')),
    name            TEXT NOT NULL,              -- kebab-case for skills, topic slug for knowledge
    domain          TEXT,                       -- e.g. 'entitlements', 'onboarding' (knowledge only)
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'pending_review', 'approved', 'rejected', 'archived')),
    current_version INT NOT NULL DEFAULT 1,
    created_by      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata        JSONB NOT NULL DEFAULT '{}',
    tags            TEXT[] NOT NULL DEFAULT '{}',

    UNIQUE (type, name)
);

CREATE INDEX idx_contributions_type ON contributions(type);
CREATE INDEX idx_contributions_status ON contributions(status);
CREATE INDEX idx_contributions_domain ON contributions(domain);
CREATE INDEX idx_contributions_tags ON contributions USING GIN(tags);
CREATE INDEX idx_contributions_metadata ON contributions USING GIN(metadata);

-- ============================================================================
-- Versions: immutable, append-only — NEVER update or delete rows here
-- ============================================================================
CREATE TABLE IF NOT EXISTS contribution_versions (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contribution_id BIGINT NOT NULL REFERENCES contributions(id) ON DELETE CASCADE,
    version         INT NOT NULL,
    content         TEXT NOT NULL,              -- the markdown body (SKILL.md body or knowledge doc)
    frontmatter     JSONB NOT NULL DEFAULT '{}',-- parsed YAML frontmatter
    files           JSONB NOT NULL DEFAULT '{}',-- additional files: {"evals/grant.yaml": "...", "reference/users.md": "..."}
    content_sha256  TEXT NOT NULL,
    created_by      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    change_summary  TEXT,                       -- what changed in this version

    UNIQUE (contribution_id, version)
);

CREATE INDEX idx_versions_contribution ON contribution_versions(contribution_id);

-- ============================================================================
-- Approvals: audit trail — who approved/rejected what, when, why
-- ============================================================================
CREATE TABLE IF NOT EXISTS approvals (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contribution_id BIGINT NOT NULL REFERENCES contributions(id) ON DELETE CASCADE,
    version         INT NOT NULL,
    decision        TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    decided_by      TEXT NOT NULL,
    reason          TEXT,
    decided_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_approvals_contribution ON approvals(contribution_id);

-- ============================================================================
-- Full-text search index on version content
-- ============================================================================
ALTER TABLE contribution_versions
    ADD COLUMN IF NOT EXISTS content_tsv TSVECTOR
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

CREATE INDEX idx_versions_fts ON contribution_versions USING GIN(content_tsv);

-- ============================================================================
-- Future: vector embedding column for semantic search
-- ============================================================================
-- ALTER TABLE contribution_versions ADD COLUMN embedding vector(1536);
-- CREATE INDEX idx_versions_vector ON contribution_versions USING ivfflat (embedding vector_cosine_ops);

-- ============================================================================
-- Helper view: latest approved version of each contribution
-- ============================================================================
CREATE OR REPLACE VIEW active_contributions AS
SELECT
    c.id,
    c.type,
    c.name,
    c.domain,
    c.status,
    c.tags,
    c.metadata,
    c.created_by,
    v.version,
    v.content,
    v.frontmatter,
    v.files,
    v.content_sha256,
    v.created_at AS version_created_at
FROM contributions c
JOIN contribution_versions v
    ON v.contribution_id = c.id
    AND v.version = c.current_version
WHERE c.status = 'approved';
