"""Generate synthetic company dataset for Decision-Trace.

Creates:
1. data/company.db (SQLite)
2. data/tickets.csv (~80 tickets with buried decisions)
3. data/meeting_notes/ (~12 Markdown files)
4. data/GROUND_TRUTH.md (eval reference)
"""

import csv
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MEETINGS_DIR = DATA_DIR / "meeting_notes"


def create_sqlite_database():
    """Create data/company.db with ~15 people, 4 teams, 6 projects, 12 systems."""
    db_path = DATA_DIR / "company.db"
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE teams (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        department TEXT NOT NULL,
        lead_id INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE people (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        role TEXT NOT NULL,
        team_id INTEGER,
        start_date TEXT NOT NULL,
        leave_date TEXT,
        FOREIGN KEY(team_id) REFERENCES teams(id)
    )
    """)

    cur.execute("""
    CREATE TABLE projects (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        description TEXT NOT NULL,
        status TEXT NOT NULL,
        lead_id INTEGER,
        FOREIGN KEY(lead_id) REFERENCES people(id)
    )
    """)

    cur.execute("""
    CREATE TABLE systems (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        system_type TEXT NOT NULL,
        vendor TEXT NOT NULL,
        owner_id INTEGER,
        status TEXT NOT NULL,
        FOREIGN KEY(owner_id) REFERENCES people(id)
    )
    """)

    # 4 Teams
    teams = [
        (1, "Core Infrastructure", "Engineering", 1),
        (2, "Data Platform", "Data & Analytics", 3),
        (3, "Security & IAM", "Information Security", 4),
        (4, "Developer Experience", "Engineering", 8),
    ]
    cur.executemany("INSERT INTO teams VALUES (?, ?, ?, ?)", teams)

    # 15 People (Marcus Aurelius has left and still owns Elasticsearch)
    people = [
        (
            1,
            "Alice Vance",
            "alice.vance@novascale.io",
            "Principal Platform Engineer",
            1,
            "2022-03-01",
            None,
        ),
        (
            2,
            "Bob Martin",
            "bob.martin@novascale.io",
            "Senior Staff SRE",
            1,
            "2022-06-15",
            None,
        ),
        (
            3,
            "Carlos Mendez",
            "carlos.mendez@novascale.io",
            "Staff Data Engineer",
            2,
            "2023-01-10",
            None,
        ),
        (
            4,
            "Diana Prince",
            "diana.prince@novascale.io",
            "Security Architect",
            3,
            "2021-08-01",
            None,
        ),
        (
            5,
            "Evan Wright",
            "evan.wright@novascale.io",
            "Senior Backend Engineer",
            1,
            "2023-04-12",
            None,
        ),
        (
            6,
            "Fiona Gallagher",
            "fiona.gallagher@novascale.io",
            "Lead Analytics Engineer",
            2,
            "2022-11-01",
            None,
        ),
        (
            7,
            "George Clark",
            "george.clark@novascale.io",
            "DevOps Engineer",
            4,
            "2023-09-01",
            None,
        ),
        (
            8,
            "Hannah Abbott",
            "hannah.abbott@novascale.io",
            "Frontend Tech Lead",
            4,
            "2022-01-20",
            None,
        ),
        (
            9,
            "Ian Malcolm",
            "ian.malcolm@novascale.io",
            "Distributed Systems Architect",
            1,
            "2021-05-10",
            None,
        ),
        (
            10,
            "Julia Roberts",
            "julia.roberts@novascale.io",
            "Identity & Access Lead",
            3,
            "2022-07-01",
            None,
        ),
        (
            11,
            "Kevin Flynn",
            "kevin.flynn@novascale.io",
            "Observability Lead",
            1,
            "2023-02-15",
            None,
        ),
        (
            12,
            "Laura Croft",
            "laura.croft@novascale.io",
            "Cloud Operations Lead",
            1,
            "2022-04-01",
            None,
        ),
        (
            13,
            "Marcus Aurelius",
            "marcus.aurelius@novascale.io",
            "Former Staff Architect",
            1,
            "2021-01-10",
            "2025-11-30",
        ),
        (
            14,
            "Nina Simone",
            "nina.simone@novascale.io",
            "Data Pipeline Engineer",
            2,
            "2023-08-15",
            None,
        ),
        (
            15,
            "Oliver Queen",
            "oliver.queen@novascale.io",
            "CI/CD Specialist",
            4,
            "2023-03-01",
            None,
        ),
    ]
    cur.executemany("INSERT INTO people VALUES (?, ?, ?, ?, ?, ?, ?)", people)

    # 6 Projects
    projects = [
        (
            1,
            "Project Horizon",
            "Session Layer Modernization and Cache Migration",
            "active",
            1,
        ),
        (
            2,
            "Project Nexus",
            "Real-time Event Streaming Spine across Microservices",
            "active",
            2,
        ),
        (
            3,
            "Project Titan",
            "Next-generation Analytics Warehouse and Aggregations",
            "active",
            3,
        ),
        (
            4,
            "Project Shield",
            "Zero Trust Auth Gateway and Enterprise SSO",
            "active",
            10,
        ),
        (
            5,
            "Project Beacon",
            "Unified Telemetry, Distributed Tracing and APM",
            "active",
            11,
        ),
        (
            6,
            "Project Velocity",
            "Modern Containerized CI/CD Delivery Pipeline",
            "active",
            15,
        ),
    ]
    cur.executemany("INSERT INTO projects VALUES (?, ?, ?, ?, ?)", projects)

    # 12 Systems (Elasticsearch owned by Marcus Aurelius who left)
    systems = [
        (1, "Postgres", "database", "PostgreSQL Global Development Group", 5, "active"),
        (2, "Redis", "cache", "Redis Ltd", 1, "active"),
        (3, "ClickHouse", "database", "ClickHouse Inc", 3, "active"),
        (4, "Keycloak", "iam", "Red Hat", 10, "active"),
        (5, "Kafka", "event-streaming", "Apache Software Foundation", 1, "active"),
        (6, "RabbitMQ", "message-broker", "VMware", 2, "active"),
        (7, "Elasticsearch", "search-engine", "Elastic NV", 13, "active"),
        (
            8,
            "Kubernetes",
            "container-orchestration",
            "Cloud Native Computing Foundation",
            12,
            "active",
        ),
        (9, "Snowflake", "data-warehouse", "Snowflake Inc", 6, "active"),
        (10, "Vault", "secrets-management", "HashiCorp", 4, "active"),
        (
            11,
            "Prometheus",
            "monitoring",
            "Cloud Native Computing Foundation",
            11,
            "active",
        ),
        (12, "Datadog", "observability", "Datadog Inc", 11, "active"),
    ]
    cur.executemany("INSERT INTO systems VALUES (?, ?, ?, ?, ?, ?)", systems)

    conn.commit()
    conn.close()
    print(f"Created SQLite database at {db_path}")


def create_tickets_csv():
    """Create data/tickets.csv with ~80 tickets including 12 buried decisions."""
    csv_path = DATA_DIR / "tickets.csv"

    # Routine ticket title templates for non-decision tickets
    routine_templates = [
        (
            "High CPU utilization on worker pods during scheduled sync",
            "Kubernetes",
            "open",
            "Alice Vance",
            "Bob Martin",
        ),
        (
            "SSL certificate renewal for internal load balancers",
            "Kubernetes",
            "closed",
            "Laura Croft",
            "Laura Croft",
        ),
        (
            "Optimize slow B-tree index on user accounts table",
            "Postgres",
            "closed",
            "Evan Wright",
            "Evan Wright",
        ),
        (
            "Connection timeout when scraping staging metric endpoints",
            "Prometheus",
            "closed",
            "Kevin Flynn",
            "Kevin Flynn",
        ),
        (
            "Missing traces on checkout service downstream call",
            "Datadog",
            "closed",
            "Hannah Abbott",
            "Kevin Flynn",
        ),
        (
            "Update CORS headers for mobile client authentication",
            "Keycloak",
            "closed",
            "Hannah Abbott",
            "Julia Roberts",
        ),
        (
            "Rate limit threshold tuning for public signup endpoints",
            "Redis",
            "closed",
            "Alice Vance",
            "Alice Vance",
        ),
        (
            "Consumer lag spike on payments topic during month-end",
            "Kafka",
            "closed",
            "Bob Martin",
            "Carlos Mendez",
        ),
        (
            "Dead letter queue alert triggered on inventory notifications",
            "RabbitMQ",
            "closed",
            "Bob Martin",
            "Bob Martin",
        ),
        (
            "Cluster disk watermark alert on log aggregation index",
            "Elasticsearch",
            "closed",
            "Oliver Queen",
            "Carlos Mendez",
        ),
        (
            "Warehouse auto-suspend timeout reduction to control cloud spend",
            "Snowflake",
            "closed",
            "Fiona Gallagher",
            "Fiona Gallagher",
        ),
        (
            "Rotate root token for transit secrets engine",
            "Vault",
            "closed",
            "Diana Prince",
            "Diana Prince",
        ),
        (
            "Partition pruning failure on daily analytics rollup view",
            "ClickHouse",
            "closed",
            "Nina Simone",
            "Carlos Mendez",
        ),
        (
            "Add automated linter step to deployment pipeline",
            "Kubernetes",
            "closed",
            "George Clark",
            "Oliver Queen",
        ),
        (
            "Node pool autoscaling delay during morning burst",
            "Kubernetes",
            "open",
            "Laura Croft",
            "Laura Croft",
        ),
    ]

    tickets = []

    # 1. Buried Decision Tickets (12 tickets)
    buried_decisions = [
        # Chain 1: TICK-101 & TICK-102
        (
            101,
            "Severe latency on Postgres session store under peak load",
            "closed",
            "2026-02-01",
            "2026-02-03",
            "Evan Wright",
            "Alice Vance",
            "Redis",
            (
                "After profiling connection exhaustion on Postgres under peak user load, Alice Vance decided: "
                "Migrate session storage from Postgres to Redis cluster to eliminate database connection pool contention. "
                "System: Redis."
            ),
        ),
        (
            102,
            "Redis session cluster operational maintenance and failover complexity",
            "closed",
            "2026-05-10",
            "2026-05-12",
            "Bob Martin",
            "Alice Vance",
            "Keycloak",
            (
                "Given recurring operational failover complexity of standalone Redis clusters, Alice Vance decided: "
                "Migrate session storage to embedded Keycloak cache. "
                "This decision supersedes Migrate session storage from Postgres to Redis cluster. "
                "System: Keycloak."
            ),
        ),
        # Chain 2: TICK-103 & TICK-104
        (
            103,
            "Slow analytical queries on historical clickstream datasets",
            "closed",
            "2026-02-15",
            "2026-02-18",
            "Nina Simone",
            "Fiona Gallagher",
            "Snowflake",
            (
                "After evaluating data warehouse capacity for ad-hoc aggregations, Fiona Gallagher decided: "
                "Adopt Snowflake for analytics ETL queries to decouple reporting compute from transactional systems. "
                "System: Snowflake."
            ),
        ),
        (
            104,
            "High compute credits on daily analytics warehouse rollups",
            "closed",
            "2026-06-01",
            "2026-06-04",
            "Carlos Mendez",
            "Carlos Mendez",
            "ClickHouse",
            (
                "Due to soaring cloud warehouse compute costs and 10x slower p95 reporting queries, Carlos Mendez decided: "
                "Migrate analytics reporting queries from Snowflake to ClickHouse cluster. "
                "This decision supersedes Adopt Snowflake for analytics ETL queries. "
                "System: ClickHouse."
            ),
        ),
        # Contradiction: TICK-105 & TICK-106
        (
            105,
            "Need enterprise event bus for asynchronous order processing",
            "closed",
            "2026-03-01",
            "2026-03-04",
            "Evan Wright",
            "Alice Vance",
            "Kafka",
            (
                "To guarantee strictly-ordered replayable message streams across our microservices, Alice Vance decided: "
                "Use Kafka for all event messaging across services. "
                "System: Kafka."
            ),
        ),
        (
            106,
            "Lightweight pubsub requirements for async background tasks",
            "closed",
            "2026-04-05",
            "2026-04-08",
            "George Clark",
            "Bob Martin",
            "RabbitMQ",
            (
                "To avoid heavy JVM JVM operational overhead and complex partition management for simple workers, Bob Martin decided: "
                "Use RabbitMQ for all event messaging across services. "
                "This decision contradicts Use Kafka for all event messaging across services. "
                "System: Kafka."
            ),
        ),
        # 6 Standalone Buried Decisions
        (
            107,
            "Plaintext secret leakage risk in CI/CD pipeline variables",
            "closed",
            "2026-03-12",
            "2026-03-14",
            "Oliver Queen",
            "Diana Prince",
            "Vault",
            (
                "Following an internal audit of credentials stored in build configurations, Diana Prince decided: "
                "Store secret credentials exclusively in HashiCorp Vault instead of Kubernetes secrets. "
                "System: Vault."
            ),
        ),
        (
            108,
            "Inconsistent distributed trace propagation in checkout services",
            "closed",
            "2026-03-25",
            "2026-03-28",
            "Hannah Abbott",
            "Kevin Flynn",
            "Datadog",
            (
                "To enable end-to-end distributed transaction tracing with minimal agent configuration, Kevin Flynn decided: "
                "Standardize application traces on Datadog APM across all production services. "
                "System: Datadog."
            ),
        ),
        (
            109,
            "Cluster-wide metrics collection and automated alerts",
            "closed",
            "2026-04-20",
            "2026-04-22",
            "George Clark",
            "Laura Croft",
            "Prometheus",
            (
                "To achieve standardized Kubernetes metrics collection and alerting, Laura Croft decided: "
                "Deploy Prometheus Operator on all Kubernetes staging clusters. "
                "System: Prometheus."
            ),
        ),
        (
            110,
            "Memory pressure on legacy RabbitMQ broker during notifications spike",
            "closed",
            "2026-05-02",
            "2026-05-05",
            "Bob Martin",
            "Ian Malcolm",
            "Redis",
            (
                "After profiling message broker RAM usage during customer broadcast spikes, Ian Malcolm decided: "
                "Deprecate legacy RabbitMQ clusters in favor of native Redis PubSub for low-volume notifications. "
                "System: Redis."
            ),
        ),
        (
            111,
            "OAuth2 token issuance architecture for internal gateway",
            "closed",
            "2026-05-22",
            "2026-05-24",
            "Evan Wright",
            "Julia Roberts",
            "Keycloak",
            (
                "To streamline microservice token validation and role-based access control, Julia Roberts decided: "
                "Use Keycloak OAuth2 tokens for internal API gateway authentication. "
                "System: Keycloak."
            ),
        ),
        (
            112,
            "Replication lag and connection pool contention on primary database",
            "closed",
            "2026-06-15",
            "2026-06-18",
            "Alice Vance",
            "Evan Wright",
            "Postgres",
            (
                "To leverage native logical replication performance and query pipeline improvements, Evan Wright decided: "
                "Upgrade all production Postgres instances to version 16. "
                "System: Postgres."
            ),
        ),
    ]

    for item in buried_decisions:
        tickets.append(
            {
                "ticket_id": f"TICK-{item[0]}",
                "title": item[1],
                "status": item[2],
                "opened": item[3],
                "closed": item[4],
                "reporter": item[5],
                "assignee": item[6],
                "system": item[7],
                "comments": item[8],
            }
        )

    # Fill remaining ~68 tickets with realistic engineering activity
    import random

    random.seed(42)

    for i in range(113, 181):
        tmpl = routine_templates[(i - 113) % len(routine_templates)]
        month = (i % 8) + 1
        day = (i % 25) + 1
        opened = f"2026-{month:02d}-{day:02d}"
        closed = f"2026-{month:02d}-{min(day + 2, 28):02d}"

        comment = "Investigated root cause with team. Applied configuration fix in staging and validated telemetry. Ticket resolved."
        tickets.append(
            {
                "ticket_id": f"TICK-{i}",
                "title": f"{tmpl[0]} - Incident #{i}",
                "status": tmpl[2],
                "opened": opened,
                "closed": closed,
                "reporter": tmpl[3],
                "assignee": tmpl[4],
                "system": tmpl[1],
                "comments": comment,
            }
        )

    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ticket_id",
                "title",
                "status",
                "opened",
                "closed",
                "reporter",
                "assignee",
                "system",
                "comments",
            ],
        )
        writer.writeheader()
        writer.writerows(tickets)

    print(f"Created {len(tickets)} tickets at {csv_path}")


def create_meeting_notes():
    """Create data/meeting_notes/ with ~12 Markdown files."""
    MEETINGS_DIR.mkdir(parents=True, exist_ok=True)

    meetings = [
        (
            "2026-01-15_infrastructure_kickoff.md",
            (
                "Meeting: Q1 Infrastructure Kickoff\n"
                "Date: 2026-01-15\n"
                "Attended by: Alice Vance, Bob Martin, Laura Croft, Kevin Flynn\n"
                "Notes: Reviewed OKRs for Q1. Focus will be on database connection stability and zero-trust auth groundwork.\n"
            ),
        ),
        (
            "2026-02-10_iam_modernization.md",
            (
                "Meeting: IAM Architecture Modernization\n"
                "Date: 2026-02-10\n"
                "Attended by: Julia Roberts, Diana Prince, Alice Vance\n"
                "Notes: Evaluated Okta, Auth0, and self-hosted Keycloak. "
                "Julia Roberts decided: Adopt Keycloak for company-wide single sign-on to comply with on-premise governance constraints. "
                "System: Keycloak.\n"
            ),
        ),
        (
            "2026-03-05_data_platform_review.md",
            (
                "Meeting: Data Platform Quarterly Review\n"
                "Date: 2026-03-05\n"
                "Attended by: Carlos Mendez, Fiona Gallagher, Nina Simone\n"
                "Notes: Discussed expanding ETL streaming jobs and real-time dashboard latency requirements.\n"
            ),
        ),
        (
            "2026-04-12_observability_sync.md",
            (
                "Meeting: Observability Platform Alignment\n"
                "Date: 2026-04-12\n"
                "Attended by: Kevin Flynn, Laura Croft, Diana Prince\n"
                "Notes: Given escalating vendor licensing costs of proprietary APM tools, Kevin Flynn decided: "
                "Migrate application metrics from Datadog to Prometheus Operator. "
                "This decision supersedes Standardize application traces on Datadog APM across all production services. "
                "System: Prometheus.\n"
            ),
        ),
        (
            "2026-05-18_messaging_strategy.md",
            (
                "Meeting: Core Messaging Architecture Sync\n"
                "Date: 2026-05-18\n"
                "Attended by: Bob Martin, Alice Vance, Ian Malcolm\n"
                "Notes: Re-evaluated messaging brokers for backend services. "
                "Bob Martin reiterated: Use RabbitMQ for all event messaging across services. "
                "This decision contradicts Use Kafka for all event messaging across services. "
                "System: RabbitMQ.\n"
            ),
        ),
        (
            "2026-06-08_secrets_management.md",
            (
                "Meeting: Security Architecture Review\n"
                "Date: 2026-06-08\n"
                "Attended by: Diana Prince, Julia Roberts, Evan Wright\n"
                "Notes: Evaluated database credential rotation. "
                "Diana Prince decided: Rotate all database passwords into Vault dynamic secrets to eliminate static credentials. "
                "System: Vault.\n"
            ),
        ),
        (
            "2026-07-14_search_infrastructure_review.md",
            (
                "Meeting: Search Infrastructure Review\n"
                "Date: 2026-07-14\n"
                "Attended by: Alice Vance, Laura Croft, Carlos Mendez\n"
                "Notes: Discussed orphaned Elasticsearch cluster. The original system owner, Marcus Aurelius, "
                "left the company on 2025-11-30. System ownership needs reassignment to Core Infrastructure.\n"
            ),
        ),
        (
            "2026-08-20_container_platform_upgrade.md",
            (
                "Meeting: Container Platform Strategy\n"
                "Date: 2026-08-20\n"
                "Attended by: Laura Croft, George Clark, Oliver Queen\n"
                "Notes: Evaluated Kubernetes version lifecycle. "
                "Laura Croft decided: Standardize on Kubernetes 1.30 across all production regions to unlock gateway API controllers. "
                "System: Kubernetes.\n"
            ),
        ),
        (
            "2026-09-10_dev_experience_sync.md",
            (
                "Meeting: Developer Experience Sync\n"
                "Date: 2026-09-10\n"
                "Attended by: Hannah Abbott, George Clark, Oliver Queen\n"
                "Notes: Evaluated monorepo build caches and automated PR previews.\n"
            ),
        ),
        (
            "2026-09-28_database_reliability.md",
            (
                "Meeting: Database Reliability Working Group\n"
                "Date: 2026-09-28\n"
                "Attended by: Evan Wright, Alice Vance, Carlos Mendez\n"
                "Notes: Reviewed Postgres 16 upgrade progress and autovacuum tuning metrics.\n"
            ),
        ),
        (
            "2026-10-02_q4_planning.md",
            (
                "Meeting: Q4 Engineering Roadmapping\n"
                "Date: 2026-10-02\n"
                "Attended by: Alice Vance, Carlos Mendez, Diana Prince, Hannah Abbott\n"
                "Notes: Finalized high-priority initiatives for Q4: ClickHouse analytics migration and Vault dynamic database secrets.\n"
            ),
        ),
        (
            "2026-10-10_cloud_cost_optimization.md",
            (
                "Meeting: Cloud Cost Optimization Taskforce\n"
                "Date: 2026-10-10\n"
                "Attended by: Laura Croft, Fiona Gallagher, Bob Martin\n"
                "Notes: Reviewed monthly cloud spend reductions achieved by decommissioning Snowflake warehouses in favor of ClickHouse.\n"
            ),
        ),
    ]

    for filename, content in meetings:
        file_path = MEETINGS_DIR / filename
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    print(f"Created {len(meetings)} meeting notes in {MEETINGS_DIR}")


def create_ground_truth_markdown():
    """Create data/GROUND_TRUTH.md documenting all planted decisions and relationships."""
    truth_path = DATA_DIR / "GROUND_TRUTH.md"

    content = """# Company Brain Synthetic Ground Truth Specification

This document provides the benchmark ground truth for evaluating the Decision-Trace knowledge extraction and entity resolution pipeline against the synthetic dataset in `data/`.

---

## 1. Company Organization (SQLite `data/company.db`)
- **Company**: NovaScale Technologies
- **Teams (4)**:
  - `Core Infrastructure` (Lead: Alice Vance)
  - `Data Platform` (Lead: Carlos Mendez)
  - `Security & IAM` (Lead: Diana Prince)
  - `Developer Experience` (Lead: Hannah Abbott)
- **Projects (6)**:
  - `Project Horizon` (Lead: Alice Vance)
  - `Project Nexus` (Lead: Bob Martin)
  - `Project Titan` (Lead: Carlos Mendez)
  - `Project Shield` (Lead: Julia Roberts)
  - `Project Beacon` (Lead: Kevin Flynn)
  - `Project Velocity` (Lead: Oliver Queen)
- **Systems & Vendors (12)**:
  - `Postgres` (Owner: Evan Wright)
  - `Redis` (Owner: Alice Vance)
  - `ClickHouse` (Owner: Carlos Mendez)
  - `Keycloak` (Owner: Julia Roberts)
  - `Kafka` (Owner: Alice Vance)
  - `RabbitMQ` (Owner: Bob Martin)
  - `Elasticsearch` (Owner: Marcus Aurelius) **[OWNER-LEFT CASE]**
  - `Kubernetes` (Owner: Laura Croft)
  - `Snowflake` (Owner: Fiona Gallagher)
  - `Vault` (Owner: Diana Prince)
  - `Prometheus` (Owner: Kevin Flynn)
  - `Datadog` (Owner: Kevin Flynn)

### The Owner-Left Case (Orphaned System)
- **Person**: `Marcus Aurelius` (Former Staff Architect, Core Infrastructure)
- **Start Date**: `2021-01-10`
- **Leave Date**: `2025-11-30` (Inactive)
- **System Owned**: `Elasticsearch`
- **Audit Flag**: `Elasticsearch` is currently owned by a departed employee with no active successor assigned in SQL metadata.

---

## 2. Planted Decisions Catalog (16 Total)

| ID | Decision Title | Decided By | System | Source Document | Status |
|---|---|---|---|---|---|
| D01 | Migrate session storage from Postgres to Redis cluster | Alice Vance | Redis | `TICK-101` | Superseded by D02 |
| D02 | Migrate session storage to embedded Keycloak cache | Alice Vance | Keycloak | `TICK-102` | Accepted (Supersedes D01) |
| D03 | Adopt Snowflake for analytics ETL queries | Fiona Gallagher | Snowflake | `TICK-103` | Superseded by D04 |
| D04 | Migrate analytics reporting queries from Snowflake to ClickHouse cluster | Carlos Mendez | ClickHouse | `TICK-104` | Accepted (Supersedes D03) |
| D05 | Use Kafka for all event messaging across services | Alice Vance | Kafka | `TICK-105` | Contradicted by D06 |
| D06 | Use RabbitMQ for all event messaging across services | Bob Martin | RabbitMQ | `TICK-106` | Contradicts D05 |
| D07 | Store secret credentials exclusively in HashiCorp Vault instead of Kubernetes secrets | Diana Prince | Vault | `TICK-107` | Accepted |
| D08 | Standardize application traces on Datadog APM across all production services | Kevin Flynn | Datadog | `TICK-108` | Superseded by D14 |
| D09 | Deploy Prometheus Operator on all Kubernetes staging clusters | Laura Croft | Prometheus | `TICK-109` | Accepted |
| D10 | Deprecate legacy RabbitMQ clusters in favor of native Redis PubSub for low-volume notifications | Ian Malcolm | Redis | `TICK-110` | Accepted |
| D11 | Use Keycloak OAuth2 tokens for internal API gateway authentication | Julia Roberts | Keycloak | `TICK-111` | Accepted |
| D12 | Upgrade all production Postgres instances to version 16 | Evan Wright | Postgres | `TICK-112` | Accepted |
| D13 | Adopt Keycloak for company-wide single sign-on | Julia Roberts | Keycloak | `2026-02-10_iam_modernization.md` | Accepted |
| D14 | Migrate application metrics from Datadog to Prometheus Operator | Kevin Flynn | Prometheus | `2026-04-12_observability_sync.md` | Accepted (Supersedes D08) |
| D15 | Rotate all database passwords into Vault dynamic secrets | Diana Prince | Vault | `2026-06-08_secrets_management.md` | Accepted |
| D16 | Standardize on Kubernetes 1.30 across all production regions | Laura Croft | Kubernetes | `2026-08-20_container_platform_upgrade.md` | Accepted |

---

## 3. Ground Truth Graph Relationships

### Supersedes Relationships (`[:supersedes]`)
1. `(D02: Keycloak Session Cache) -[:supersedes]-> (D01: Redis Session Store)` [Ticket-to-Ticket]
2. `(D04: ClickHouse Reporting) -[:supersedes]-> (D03: Snowflake Analytics)` [Ticket-to-Ticket]
3. `(D14: Prometheus Metrics) -[:supersedes]-> (D08: Datadog Traces)` [Meeting-to-Ticket]

### Contradicts Relationships (`[:contradicts]`)
1. `(D06: RabbitMQ by Bob Martin) -[:contradicts]-> (D05: Kafka by Alice Vance)` [Ticket-to-Ticket, System: Kafka/RabbitMQ conflict]

### Decided By Relationships (`[:decided_by]`)
- Alice Vance -> D01, D02, D05
- Bob Martin -> D06
- Carlos Mendez -> D04
- Diana Prince -> D07, D15
- Evan Wright -> D12
- Fiona Gallagher -> D03
- Ian Malcolm -> D10
- Julia Roberts -> D11, D13
- Kevin Flynn -> D08, D14
- Laura Croft -> D09, D16
"""

    with open(truth_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Created ground truth at {truth_path}")


if __name__ == "__main__":
    create_sqlite_database()
    create_tickets_csv()
    create_meeting_notes()
    create_ground_truth_markdown()
    print("Synthetic dataset generation completed successfully.")
