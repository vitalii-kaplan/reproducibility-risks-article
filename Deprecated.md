# KNIME Deprecated Nodes

This note records how KNIME represents deprecated nodes in source code and how we should mine them.

## Main Mechanism

KNIME node deprecation is organized primarily through Eclipse extension metadata, not through Java `@Deprecated` annotations.

For ordinary nodes, the main marker is in `plugin.xml`:

```xml
<extension point="org.knime.workbench.repository.nodes">
  <node
      category-path="/..."
      deprecated="true"
      factory-class="...SomeNodeFactory">
  </node>
</extension>
```

The relevant schema is:

- `/Users/vitaly/Home/git_proj/2026-06-knime-oss/knime-workbench/org.knime.workbench.repository/schema/Node.exsd`

The schema documents that deprecated nodes are not shown in the node repository any more, but are still loaded in existing workflows. It also says that if `deprecated="true"` is set in the extension point, it does not also need to be specified in the node description XML file.

## Dynamic Node Sets

KNIME also supports deprecation for node sets:

```xml
<extension point="org.knime.workbench.repository.nodesets">
  <nodeset
      deprecated="true"
      factory-class="...SomeNodeSetFactory">
  </nodeset>
</extension>
```

The relevant schema is:

- `/Users/vitaly/Home/git_proj/2026-06-knime-oss/knime-workbench/org.knime.workbench.repository/schema/nodesets.exsd`

The schema uses the same explanation: deprecated nodes are hidden from the node repository but still loaded in existing workflows.

## Node Description XML

A second deprecation marker exists in node description XML files:

```xml
<knimeNode icon="./dectree.png" type="Learner" deprecated="true">
```

Example:

- `/Users/vitaly/Home/git_proj/2026-06-knime-oss/knime-base/org.knime.deprecated/src/org/knime/base/node/mine/decisiontree2/learner/DecisionTreeLearnerNodeFactory.xml`

This should be treated as a secondary source because extension-point deprecation is the preferred source for ordinary nodes.

## Runtime Interpretation

KNIME exposes node deprecation through `NodeFactory.isDeprecated()`.

Relevant source:

- `/Users/vitaly/Home/git_proj/2026-06-knime-oss/knime-core/org.knime.core/src/eclipse/org/knime/core/node/NodeFactory.java`

The code comments state that ordinary nodes declare deprecation through the extension-point registration. Dynamic nodes, registered through `NodeSetFactory`, can override the deprecation status in code.

KNIME also exposes deprecated nodes through:

- `/Users/vitaly/Home/git_proj/2026-06-knime-oss/knime-core/org.knime.core/src/eclipse/org/knime/core/node/extension/NodeSpecCollectionProvider.java`

Its comments define deprecated nodes as those where `NodeFactoryExtension`, `NodeSetFactoryExtension`, or the node factory provided by `NodeSetFactory` marks the node as deprecated.

## Hidden Nodes Are Different

The node extension schema also has:

```xml
hidden="true"
```

Hidden nodes are similar to deprecated nodes because they are not shown in the node repository but are still loadable in existing workflows. However, hidden nodes do not receive the deprecation label in the node name or description. Therefore, mining should keep `hidden="true"` separate from `deprecated="true"`.

## Migration And Replacement

Deprecation is separate from migration or replacement.

KNIME has at least two related mechanisms:

- `NodeFactoryClassMapper`
- `NodeMigrationRule`

Relevant schemas:

- `/Users/vitaly/Home/git_proj/2026-06-knime-oss/knime-core/org.knime.core/schema/NodeFactoryClassMapper.exsd`
- `/Users/vitaly/Home/git_proj/2026-06-knime-oss/knime-database/org.knime.workflow.migration/schema/NodeMigrationRule.exsd`

`NodeFactoryClassMapper` maps old persisted node factory class names to new implementations. `NodeMigrationRule` allows plug-ins to register workflow node migration rules. These mechanisms can be useful for studying compatibility, but they should not be counted as deprecation markers by themselves.

## Initial Mining Rules

1. Parse all `plugin.xml` files in the KNIME source snapshot.
2. Extract `<extension point="org.knime.workbench.repository.nodes">`.
3. Collect all `<node deprecated="true" factory-class="...">` entries.
4. Extract `<extension point="org.knime.workbench.repository.nodesets">`.
5. Collect all `<nodeset deprecated="true" factory-class="...">` entries.
6. Parse `*NodeFactory.xml` and other node-description XML files with `<knimeNode deprecated="true">`.
7. Keep `hidden="true"` nodes in a separate table.
8. Mine `NodeFactoryClassMapper` and `NodeMigrationRule` separately as compatibility and migration evidence, not as deprecation evidence.

## Source Snapshot

The local source snapshot used for this investigation is:

```text
/Users/vitaly/Home/git_proj/2026-06-knime-oss
```

The clone details are recorded in:

- `notes/knime-oss-source-snapshot.md`

## DONE

### Official KNIME Deprecation Mechanisms Recorded

We have identified the main source-code mechanisms that KNIME uses to represent
deprecated nodes:

- ordinary node deprecation in `plugin.xml` through
  `org.knime.workbench.repository.nodes`
- dynamic node-set deprecation in `plugin.xml` through
  `org.knime.workbench.repository.nodesets`
- secondary deprecation markers in node-description XML files,
  such as `*NodeFactory.xml`
- runtime interpretation through `NodeFactory.isDeprecated()`
- compatibility mechanisms through `NodeFactoryClassMapper`
  and `NodeMigrationRule`
- separate hidden-node metadata through `hidden="true"`

For the article, the important distinction is that deprecated nodes are not the
same as removed nodes, hidden nodes, or migrated nodes. Deprecated nodes may
still be loadable in existing workflows, but they are a warning signal for
long-term reproducibility because they indicate that a workflow depends on
components no longer recommended for normal use.

### Repository-Level Data Collected

We have enough data for a repository-level longitudinal analysis of deprecated
KNIME nodes. The main summary table is:

- `data/processed/knime_snapshots/knime_node_snapshot_summary.csv`

The data currently covers 13 source snapshots from `2018-04-03` to
`2026-06-28`, including annual checkpoints and major-version anchor dates.

Major-version anchor rows:

| Date | Version context | Registered nodes | Deprecated nodes | Deprecated node share |
|---|---|---:|---:|---:|
| `2018-04-03` | KNIME Analytics Platform 3.5.3 source-date anchor | 1301 | 193 | 14.83% |
| `2019-12-05` | KNIME Analytics Platform 4.1.0 source-date anchor | 1191 | 227 | 19.06% |
| `2023-02-22` | KNIME Analytics Platform 5.0.0 source-date anchor | 1442 | 433 | 30.03% |
| `2026-03-03` | KNIME Analytics Platform 5.11.0 source-date anchor | 1503 | 503 | 33.47% |
| `2026-06-28` | Current local source-date snapshot | 1506 | 502 | 33.33% |

This supports the claim that deprecated KNIME nodes are not rare. In the
current local source snapshot, about one third of registered ordinary KNIME
nodes in `plugin.xml` are marked as deprecated.

### Article-Relevant Interpretation

The current data supports a descriptive repository-mining section of the paper.
It can show:

- growth of deprecated-node share over time
- a major increase between the 4.x-era and 5.x-era snapshots
- coexistence of deprecated, hidden, migrated, and removed node states
- evidence that platform evolution changes the executable environment for old
  workflows

For reproducibility, the main point is not that every deprecated node breaks a
workflow. The stronger and more accurate claim is that deprecation is a
measurable compatibility-risk signal. Published workflows that depend on such
nodes may still open today, but they depend on legacy behavior, migration
support, extension availability, and future backward compatibility.

### Data-Collection Process Recorded

The data-collection protocol is recorded in:

- `Methods.md`

The current process is reproducible from the project scripts:

- `scripts/checkout_knime_oss_by_date.sh`
- `scripts/collect_knime_node_snapshot.py`
- `scripts/build_knime_node_snapshot_summary.py`

Per-snapshot extracted records are stored under:

- `data/original/knime_snapshots/<snapshot-date>/`

## TODO

### Strengthen Official KNIME Semantics

For the article, convert the source-code notes above into a concise,
citable description of KNIME node status semantics:

- what `deprecated="true"` means in the KNIME repository extension schema
- what `hidden="true"` means and why it must be counted separately
- how dynamic node sets represent deprecation
- how node-description XML relates to `plugin.xml`
- how `NodeFactoryClassMapper` and `NodeMigrationRule` support compatibility
  without being deprecation markers themselves

This section should cite or quote only short passages from the KNIME schema or
source comments and then paraphrase the rest.

### Build A Node-Level Lifecycle Table

The aggregate summary table is useful, but the article needs stronger evidence
from node-level lifecycle tracking. Create a derived table with columns such as:

```text
node_key, repo, factory_class, first_seen, last_seen,
first_deprecated, last_deprecated, ever_deprecated,
ever_hidden, removed_by_current_snapshot,
category_change_count, description_deprecated_seen
```

This would let us report how many nodes:

- became deprecated after first appearance
- remained deprecated for several years
- disappeared from later snapshots
- became hidden
- changed category
- have inconsistent deprecation evidence between `plugin.xml` and
  node-description XML

### Link Deprecated Nodes To Migration Evidence

Analyze whether deprecated nodes have explicit compatibility support:

- link deprecated node factory classes to `NodeFactoryClassMapper`
- link deprecated or replaced nodes to `NodeMigrationRule`
- count deprecated nodes with and without observed migration evidence

This is important because deprecated nodes with migration support pose a
different reproducibility risk from deprecated nodes with no visible migration
path.

### Validate A Manual Sample

Manually inspect a small sample of extracted nodes before using the results in
the paper:

- deprecated node with a migration rule
- deprecated node without a migration rule
- hidden node
- removed node
- node where `plugin.xml` and node-description XML disagree
- dynamic nodeset marked deprecated

The goal is to verify that the parser interpretation matches KNIME metadata and
to collect concrete examples for the paper.

### State Limitations Clearly

The repository-mining section should explicitly state these limitations:

- The analysis covers public `knime-oss` repositories only.
- Date-based snapshots approximate source states near selected dates; they are
  not exact binary release builds.
- Earlier dates have fewer repositories because some repositories did not yet
  exist in the local history.
- The analysis counts metadata records, not runtime execution failures.
- Deprecated does not mean broken; it indicates legacy or discouraged use.
- Hidden, removed, migrated, and deprecated are related but distinct states.

### Connect Repository Data To Published-Workflow Reproducibility

The deprecated-node data is sufficient for the KNIME repository-evolution part
of the study. To support the full paper argument, it still needs to be connected
to empirical evidence from published workflows:

- OpenAlex frequency of KNIME-related publications
- k2pweb.org workflow usage involving deprecated nodes
- audit of highly cited KNIME papers
- whether papers publish workflows
- whether papers report KNIME versions
- whether workflows can be downloaded, opened, and run in current KNIME
