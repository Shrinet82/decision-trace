"""Cypher for each Ask step. All graph work happens here; Python only assembles the rows."""

# Matching: every name the question could refer to, in one round trip
ROSTER = (
    "MATCH (n) WHERE n:Person OR n:System OR n:Decision "
    "RETURN labels(n)[0], coalesce(n.name, n.title), n.id"
)

# why / other ---------------------------------------------------------------------------------
_WHY_RETURN = (
    "OPTIONAL MATCH (d)-[r_dec:decided_by]->(p:Person) "
    "{system_match}"
    "OPTIONAL MATCH (d)-[r_tic:based_on]->(t:Ticket) "
    "OPTIONAL MATCH (d)-[r_mtg:based_on]->(m:Meeting) "
    "OPTIONAL MATCH (d)-[r_doc:based_on]->(dc:Document) "
    "OPTIONAL MATCH (d)-[r_sup:supersedes]->(d_sup:Decision) "
    "OPTIONAL MATCH (d_sup_by:Decision)-[r_supby:supersedes]->(d) "
    "OPTIONAL MATCH (d)-[r_con:contradicts]-(d_con:Decision) "
    "OPTIONAL MATCH (s)<-[r_own:owns]-(owner:Person) "
    "RETURN d.id, d.title, coalesce(d.summary, ''), coalesce(d.rationale, ''), "
    "coalesce(d.status, 'accepted'), p.name, s.name, t.ticket_id, t.title, m.title, m.date, "
    "d_sup.id, d_sup.title, d_sup_by.id, d_sup_by.title, d_con.id, d_con.title, "
    "owner.name, coalesce(owner.is_active, true), coalesce(owner.leave_date, ''), dc.title, dc.date"
)
WHY_BY_IDS = "MATCH (d:Decision) WHERE d.id IN $decision_ids " + _WHY_RETURN.format(
    system_match="OPTIONAL MATCH (d)-[r_sys:about_system]->(s:System) "
)
WHY_BY_SYSTEMS = (
    "MATCH (d:Decision)-[r_sys:about_system]->(s:System) WHERE s.name IN $system_names "
    + _WHY_RETURN.format(system_match="")
)
WHY_BY_PEOPLE = (
    "MATCH (d:Decision)-[:decided_by]->(pp:Person) WHERE pp.name IN $people_names "
    + _WHY_RETURN.format(system_match="OPTIONAL MATCH (d)-[r_sys:about_system]->(s:System) ")
)
WHY_OWNERS = (
    "MATCH (s:System) WHERE s.name IN $system_names "
    "OPTIONAL MATCH (s)<-[r:owns]-(p:Person) "
    "RETURN s.name, p.name, coalesce(p.is_active, true), coalesce(p.leave_date, '')"
)

# impact --------------------------------------------------------------------------------------
# Decisions on the system plus every decision in their supersedes chains (both directions).
IMPACT_DECISIONS = (
    "MATCH (s:System)<-[:about_system]-(d:Decision) WHERE toLower(s.name) = toLower($name) "
    "WITH collect(DISTINCT d) AS direct "
    "UNWIND direct AS d "
    "OPTIONAL MATCH (d)-[:supersedes*1..5]-(c:Decision) "
    "WITH direct, collect(DISTINCT c) AS chained "
    "WITH direct + chained AS ds "
    "UNWIND ds AS x "
    "WITH DISTINCT x "
    "OPTIONAL MATCH (x)-[:decided_by]->(p:Person) "
    "WITH x, collect(DISTINCT p {.name, .role, .is_active, .leave_date}) AS deciders "
    "OPTIONAL MATCH (x)-[:about_system]->(xs:System) "
    "WITH x, deciders, collect(DISTINCT xs.name) AS systems "
    "OPTIONAL MATCH (x)-[:supersedes]->(old:Decision) "
    "WITH x, deciders, systems, collect(DISTINCT old.id) AS supersedes "
    "OPTIONAL MATCH (x)-[:contradicts]-(k:Decision) "
    "WITH x, deciders, systems, supersedes, collect(DISTINCT k.id) AS contradicts "
    "OPTIONAL MATCH (x)-[:based_on]->(src) "
    "RETURN x.id, x.title, x.decided_on, deciders, systems, supersedes, contradicts, "
    "collect(DISTINCT [labels(src)[0], coalesce(src.ticket_id, src.title), src.title, "
    "coalesce(src.date, src.opened)])"
)
# Owner, ticket participants, and teams/projects two hops away (system <- owner -> team/project)
IMPACT_PEOPLE = (
    "MATCH (s:System) WHERE toLower(s.name) = toLower($name) "
    "OPTIONAL MATCH (s)<-[:owns]-(o:Person) "
    "WITH s, collect(DISTINCT o {.name, .role, .is_active, .leave_date}) AS owners "
    "OPTIONAL MATCH (s)<-[:mentions]-(t:Ticket)-[:raised_by|assigned_to]->(tp:Person) "
    "WITH s, owners, collect(DISTINCT [tp.name, tp.role, tp.is_active, tp.leave_date, t.ticket_id]) AS ticket_people "
    "OPTIONAL MATCH (s)<-[:owns]-(op:Person)-[r2:member_of|leads]->(x) WHERE x:Team OR x:Project "
    "RETURN owners, ticket_people, collect(DISTINCT [labels(x)[0], x.name, op.name, type(r2)])"
)
IMPACT_TICKETS = (
    "MATCH (s:System)<-[:mentions]-(t:Ticket) WHERE toLower(s.name) = toLower($name) "
    "RETURN t.ticket_id, t.title, t.status, t.opened, t.closed ORDER BY t.opened DESC LIMIT 25"
)

# expertise -----------------------------------------------------------------------------------
# Evidence per person on one system: decided a decision about it, owns it, attended a meeting that
# is a source of one of its decisions or mentions it by name, or raised / was assigned a ticket
# that mentions it. Each list holds [person, evidence key] pairs; Python counts and weights them.
EXPERTISE = (
    "MATCH (s:System) WHERE toLower(s.name) = toLower($name) "
    "OPTIONAL MATCH (s)<-[:about_system]-(d:Decision)-[:decided_by]->(p1:Person) "
    "WITH s, collect(DISTINCT [p1 {.name, .role, .is_active, .leave_date}, d.id]) AS decided "
    "OPTIONAL MATCH (s)<-[:owns]-(p2:Person) "
    "WITH s, decided, collect(DISTINCT [p2 {.name, .role, .is_active, .leave_date}, s.name]) AS owns "
    "OPTIONAL MATCH (s)<-[:about_system]-(:Decision)-[:based_on]->(m1:Meeting)-[:attended_by]->(p3:Person) "
    "WITH s, decided, owns, collect(DISTINCT [p3 {.name, .role, .is_active, .leave_date}, m1.title]) AS meet_src "
    "OPTIONAL MATCH (m2:Meeting)-[:attended_by]->(p4:Person) "
    "WHERE toLower(coalesce(m2.body, '')) CONTAINS toLower(s.name) "
    "WITH s, decided, owns, meet_src, collect(DISTINCT [p4 {.name, .role, .is_active, .leave_date}, m2.title]) AS meet_text "
    "OPTIONAL MATCH (s)<-[:mentions]-(t:Ticket)-[:raised_by|assigned_to]->(p5:Person) "
    "RETURN decided, owns, meet_src, meet_text, "
    "collect(DISTINCT [p5 {.name, .role, .is_active, .leave_date}, t.ticket_id])"
)

# status --------------------------------------------------------------------------------------
STATUS_DECISIONS = (
    "MATCH (d:Decision) "
    "OPTIONAL MATCH (d)-[:decided_by]->(p:Person) "
    "WITH d, collect(DISTINCT p.name) AS deciders "
    "OPTIONAL MATCH (d)-[:about_system]->(s:System) "
    "WITH d, deciders, collect(DISTINCT s.name) AS systems "
    "OPTIONAL MATCH (d)-[:contradicts]->(k:Decision) "
    "WITH d, deciders, systems, collect(DISTINCT k.id) AS contradicts "
    "OPTIONAL MATCH (d)-[:supersedes]->(o:Decision) "
    "WITH d, deciders, systems, contradicts, collect(DISTINCT o.id) AS supersedes "
    "OPTIONAL MATCH (d)-[:based_on]->(src) "
    "RETURN d.id, d.title, d.decided_on, deciders, systems, contradicts, supersedes, "
    "collect(DISTINCT [labels(src)[0], coalesce(src.ticket_id, src.title), src.title, "
    "coalesce(src.date, src.opened)])"
)
STATUS_SYSTEMS = (
    "MATCH (s:System) "
    "OPTIONAL MATCH (s)<-[:owns]-(o:Person) "
    "RETURN s.name, collect(DISTINCT o {.name, .role, .is_active, .leave_date}) ORDER BY s.name"
)
