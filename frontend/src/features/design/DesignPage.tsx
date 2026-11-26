import type { ColumnDef } from '@tanstack/react-table';
import { Download, GitBranch, Play, Plus, Settings2, Trash2 } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import {
  AIFooter,
  Avatar,
  Badge,
  Button,
  CodeBlock,
  DataTable,
  Diff,
  EmptyState,
  EvidenceChip,
  FilterBar,
  IconButton,
  KeyValueList,
  Kbd,
  MetricTile,
  Modal,
  Page,
  PageHeader,
  Panel,
  ProgressBar,
  ScoreRing,
  SearchInput,
  SegmentedControl,
  Select,
  SeverityBadge,
  Skeleton,
  SkeletonRows,
  SkeletonTile,
  Slider,
  Sparkline,
  Stepper,
  StatusDot,
  Switch,
  Tabs,
  TextArea,
  TextInput,
  Timeline,
  Tooltip,
  type Severity,
  type StepItem,
} from '@/components/ui';
import { registerInspector } from '@/features/inspector/registry';
import { useUI } from '@/store/ui';

function DemoInspector({ id }: { id: string }) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Inspector demo</h2>
        <p className="mt-1 text-sm text-fg-2">
          Every asset, finding and graph node opens in this same right-hand drawer, so the pattern is reused across all modules.
        </p>
      </div>
      <KeyValueList
        items={[
          { label: 'Selected', value: id, mono: true },
          { label: 'Owner', value: <span className="inline-flex items-center gap-2"><Avatar name="Rohan Kulkarni" size={20} />Rohan Kulkarni</span> },
          { label: 'Lifecycle', value: <Badge tone="high" dot>Extended support</Badge> },
        ]}
      />
      <AIFooter confidence={0.91} evidenceCount={4} />
    </div>
  );
}
registerInspector('design-demo', { label: 'Inspector', Component: DemoInspector });

interface Row {
  id: string;
  name: string;
  domain: string;
  tech: string;
  severity: Severity;
  deps: number;
}

const ROWS: Row[] = [
  { id: 'APP-0001', name: 'SAP S/4HANA Finance', domain: 'Finance', tech: 'SAP S/4HANA 2022', severity: 'low', deps: 31 },
  { id: 'APP-0007', name: 'Guidewire ClaimCenter', domain: 'Claims', tech: 'Java 8 · Oracle 12c', severity: 'critical', deps: 44 },
  { id: 'APP-0012', name: 'MuleSoft Anypoint', domain: 'Integration', tech: 'Mule 4.4', severity: 'medium', deps: 58 },
  { id: 'APP-0019', name: 'Policy Admin Core', domain: 'Policy', tech: 'Duck Creek · SQL Server 2014', severity: 'high', deps: 37 },
  { id: 'APP-0023', name: 'Claims Mainframe Core', domain: 'Claims', tech: 'COBOL · z/OS', severity: 'high', deps: 26 },
  { id: 'APP-0031', name: 'Salesforce Service Cloud', domain: 'Customer', tech: 'Salesforce', severity: 'low', deps: 22 },
  { id: 'APP-0038', name: 'Snowflake Data Cloud', domain: 'Data', tech: 'Snowflake', severity: 'low', deps: 40 },
];

const columns: ColumnDef<Row>[] = [
  { accessorKey: 'id', header: 'ID', size: 1, cell: (c) => <span className="font-mono text-xs text-fg-2">{c.getValue<string>()}</span> },
  { accessorKey: 'name', header: 'Application', size: 3, cell: (c) => <span className="font-medium">{c.getValue<string>()}</span> },
  { accessorKey: 'domain', header: 'Domain', size: 1.4 },
  { accessorKey: 'tech', header: 'Tech stack', size: 2.4, cell: (c) => <span className="text-fg-2">{c.getValue<string>()}</span> },
  { accessorKey: 'severity', header: 'Risk', size: 1.2, cell: (c) => <SeverityBadge severity={c.getValue<Severity>()} /> },
  { accessorKey: 'deps', header: 'Dependents', size: 1, cell: (c) => <span className="num font-mono text-xs">{c.getValue<number>()}</span> },
];

const APPROVED = `resource "azurerm_cognitive_account" "openai" {
  name                          = "oai-claims-prod"
  kind                          = "OpenAI"
  sku_name                      = "S0"
  public_network_access_enabled = false
  custom_subdomain_name         = "oai-claims-prod"
}

resource "azurerm_private_endpoint" "openai" {
  name      = "pe-oai-claims-prod"
  subnet_id = azurerm_subnet.private.id
}`;

const DEPLOYED = `resource "azurerm_cognitive_account" "openai" {
  name                          = "oai-claims-prod"
  kind                          = "OpenAI"
  sku_name                      = "S0"
  public_network_access_enabled = true
  custom_subdomain_name         = "oai-claims-prod"
}`;

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="mb-8 scroll-mt-6">
      <h2 className="micro mb-3 border-b border-line-subtle pb-2">{title}</h2>
      {children}
    </section>
  );
}

export default function DesignPage() {
  const { toast, openInspector, setCommandOpen, theme, toggleTheme } = useUI();
  const [tab, setTab] = useState('overview');
  const [seg, setSeg] = useState('graph');
  const [on, setOn] = useState(true);
  const [slider, setSlider] = useState(99.9);
  const [q, setQ] = useState('');
  const [sel, setSel] = useState('all');
  const [filters, setFilters] = useState<Record<string, string>>({ domain: 'Claims' });
  const [modal, setModal] = useState(false);
  const [loading, setLoading] = useState(false);

  const steps: StepItem[] = [
    { id: '1', label: 'Parsing documents', state: 'done', durationMs: 900, detail: '60 documents · 412 sections' },
    { id: '2', label: 'Extracting entities', state: 'done', durationMs: 1400, detail: '286 systems, 94 APIs, 41 data stores' },
    { id: '3', label: 'Resolving relationships', state: 'active', detail: 'Reconciling 7 conflicting statements' },
    { id: '4', label: 'Scoring risk', state: 'pending' },
  ];

  return (
    <Page>
      <PageHeader
        title="Design system"
        description="Every ArchIQ component in its states. Used for QA and as the reference for new modules."
        freshness="Rendered just now"
        actions={
          <Button variant="primary" leading={<Play className="h-3.5 w-3.5" />} onClick={() => toast({ title: 'Run started', description: 'Assessment queued for the Claims domain.', tone: 'success' })}>
            Run assessment
          </Button>
        }
        secondary={
          <Button onClick={toggleTheme}>{theme === 'dark' ? 'Dark' : 'Light'} theme</Button>
        }
      />

      <Section id="buttons" title="Buttons">
        <div className="flex flex-wrap items-center gap-2.5">
          <Button variant="primary">Primary</Button>
          <Button>Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger" leading={<Trash2 className="h-3.5 w-3.5" />}>Danger</Button>
          <Button variant="primary" loading>Generating</Button>
          <Button disabled>Disabled</Button>
          <Button size="sm" leading={<Plus className="h-3.5 w-3.5" />}>Small</Button>
          <Button size="lg" variant="primary" leading={<GitBranch className="h-4 w-4" />}>Large</Button>
          <IconButton label="Settings"><Settings2 className="h-4 w-4" /></IconButton>
          <IconButton label="Download" variant="secondary"><Download className="h-4 w-4" /></IconButton>
          <Kbd>⌘</Kbd><Kbd>K</Kbd>
        </div>
      </Section>

      <Section id="badges" title="Badges, status and severity">
        <div className="flex flex-wrap items-center gap-2.5">
          <Badge>Neutral</Badge>
          <Badge tone="accent">Accent</Badge>
          <Badge tone="healthy" dot>Supported</Badge>
          <Badge tone="high" dot>Extended</Badge>
          <Badge tone="critical" dot>End of life</Badge>
          <Badge mono>STD-SEC-014</Badge>
          {(['critical', 'high', 'medium', 'low', 'info'] as Severity[]).map((s) => <SeverityBadge key={s} severity={s} />)}
          <span className="ml-2 flex items-center gap-2 text-xs text-fg-2"><StatusDot pulse /> Live</span>
          <Avatar name="Avadhi Jain" /><Avatar name="Rohan Kulkarni" /><Avatar name="Ananya Rao" /><Avatar name="Dev Patel" />
          <EvidenceChip kind="doc" label="HLD-Claims-Intake-v3.pdf" />
          <EvidenceChip kind="rule" label="STD-SEC-014" />
        </div>
      </Section>

      <Section id="metrics" title="Metric tiles, score rings and progress">
        <div className="grid grid-cols-4 gap-3">
          <MetricTile label="Applications" value="71" delta={3} deltaGoodWhen="up" spark={[52, 54, 55, 58, 60, 66, 71]} />
          <MetricTile label="Critical findings" value="12" delta={-8} spark={[22, 21, 19, 18, 16, 14, 12]} sparkTone="critical" />
          <MetricTile label="Availability" value="99.94" unit="%" delta={0} hint="rolling 30 days" />
          <MetricTile label="Remediation" value="2.4" unit="M USD" delta={5} spark={[1.1, 1.3, 1.8, 2, 2.1, 2.2, 2.4]} />
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-8">
          <ScoreRing score={86} label="health" />
          <ScoreRing score={61} label="health" />
          <ScoreRing score={38} label="health" />
          <ScoreRing score={74} label="debt" invert size={72} stroke={6} />
          <div className="w-64 space-y-3">
            <ProgressBar value={72} label="Wave 1" />
            <ProgressBar value={45} tone="high" />
            <ProgressBar value={18} tone="critical" />
          </div>
          <Sparkline data={[3, 5, 4, 8, 7, 11, 9, 14]} width={140} height={36} />
        </div>
      </Section>

      <Section id="inputs" title="Inputs and controls">
        <div className="grid grid-cols-3 gap-6">
          <div className="space-y-3">
            <SearchInput value={q} onChange={setQ} placeholder="Search assets" shortcut="/" />
            <TextInput placeholder="Plain text field" />
            <TextArea rows={3} placeholder="Describe the business goal…" />
          </div>
          <div className="space-y-4">
            <Select value={sel} onValueChange={setSel} options={[{ value: 'all', label: 'All domains' }, { value: 'claims', label: 'Claims' }, { value: 'policy', label: 'Policy admin' }]} />
            <SegmentedControl value={seg} onChange={setSeg} options={[{ value: 'graph', label: 'Graph' }, { value: 'table', label: 'Table' }, { value: 'map', label: 'Map' }]} />
            <div className="flex items-center gap-2 text-sm"><Switch checked={on} onCheckedChange={setOn} label="Continuous scan" /> Continuous scan</div>
          </div>
          <div className="space-y-4">
            <Slider label="Availability target" value={slider} onChange={setSlider} min={99} max={99.999} step={0.001} format={(v) => `${v.toFixed(3)}%`} />
          </div>
        </div>
        <div className="mt-5">
          <FilterBar
            filters={[
              { key: 'domain', label: 'Domain', options: [{ value: 'Claims', label: 'Claims' }, { value: 'Policy', label: 'Policy' }] },
              { key: 'lifecycle', label: 'Lifecycle', options: [{ value: 'eol', label: 'End of life' }, { value: 'ext', label: 'Extended' }] },
            ]}
            values={filters}
            onChange={(k, v) => setFilters((f) => ({ ...f, [k]: v }))}
            search={q}
            onSearch={setQ}
            searchPlaceholder="Filter applications"
          />
        </div>
      </Section>

      <Section id="tabs" title="Tabs">
        <Tabs
          value={tab}
          onValueChange={setTab}
          items={[
            { value: 'overview', label: 'Overview', content: <p className="text-sm text-fg-2">Tab content renders here with a 16px top gap.</p> },
            { value: 'deps', label: 'Dependencies', count: 14, content: <p className="text-sm text-fg-2">14 upstream and downstream dependencies.</p> },
            { value: 'docs', label: 'Documents', count: 6, content: <p className="text-sm text-fg-2">6 linked documents.</p> },
          ]}
        />
      </Section>

      <Section id="table" title="Data table (virtualised, sortable, keyboard navigable)">
        <DataTable data={ROWS} columns={columns} getRowId={(r) => r.id} onRowClick={(r) => openInspector({ kind: 'design-demo', id: r.id })} ariaLabel="Applications" />
      </Section>

      <Section id="loading" title="Loading, empty and AI trace">
        <div className="grid grid-cols-3 gap-4">
          <Panel title="Skeletons" actions={<Button size="sm" loading={loading} onClick={() => { setLoading(true); setTimeout(() => setLoading(false), 1500); }}>Simulate</Button>}>
            <div className="space-y-3"><SkeletonTile /><SkeletonRows rows={4} /><Skeleton className="h-24" /></div>
          </Panel>
          <Panel title="Empty state">
            <EmptyState title="No drift detected" description="Everything deployed in this scope matches the approved design." action={<Button size="sm">Re-scan now</Button>} />
          </Panel>
          <Panel title="AI progress trace">
            <Stepper steps={steps} />
            <AIFooter className="mt-4" confidence={0.91} evidenceCount={12} />
          </Panel>
        </div>
      </Section>

      <Section id="timeline" title="Timeline and key-value list">
        <div className="grid grid-cols-2 gap-4">
          <Panel title="Recent AI activity">
            <Timeline
              items={[
                { id: '1', title: 'Assessment completed for Claims domain', meta: '4 min ago', tone: 'accent', body: '31 findings, 4 critical' },
                { id: '2', title: 'Drift scan found public endpoint', meta: '22 min ago', tone: 'critical', body: 'oai-claims-prod' },
                { id: '3', title: 'ADR-0042 generated: event-driven claims intake', meta: '2 h ago', tone: 'healthy' },
              ]}
            />
          </Panel>
          <Panel title="Key-value list">
            <KeyValueList items={[{ label: 'Owner', value: 'Claims Platform' }, { label: 'Hosting', value: 'Azure · West Europe' }, { label: 'Resource ID', value: 'rg-claims-prod/oai-claims-prod', mono: true }, { label: 'Criticality', value: <SeverityBadge severity="high" /> }]} />
          </Panel>
        </div>
      </Section>

      <Section id="code" title="Code block and diff">
        <div className="grid grid-cols-2 gap-4">
          <CodeBlock code={APPROVED} language="hcl" filename="main.tf" maxHeight={300} />
          <Diff left={APPROVED} right={DEPLOYED} />
        </div>
      </Section>

      <Section id="overlays" title="Overlays">
        <div className="flex flex-wrap gap-2.5">
          <Button onClick={() => openInspector({ kind: 'design-demo', id: 'APP-0007' })}>Open inspector drawer</Button>
          <Button onClick={() => setModal(true)}>Open modal</Button>
          <Button onClick={() => setCommandOpen(true)}>Command palette <Kbd>⌘K</Kbd></Button>
          <Button onClick={() => toast({ title: 'Report exported', description: 'impact-report.md saved', tone: 'success' })}>Toast</Button>
          <Tooltip content="Tooltips are used for truncated text and icon buttons"><Button variant="outline">Hover for tooltip</Button></Tooltip>
        </div>
        <Modal open={modal} onOpenChange={setModal} title="Accept as exception" description="Exceptions expire automatically and are reviewed by the design authority." footer={<><Button onClick={() => setModal(false)}>Cancel</Button><Button variant="primary" onClick={() => { setModal(false); toast({ title: 'Exception recorded', tone: 'success' }); }}>Accept exception</Button></>}>
          <div className="space-y-3">
            <TextInput placeholder="Justification" />
            <Select value={sel} onValueChange={setSel} options={[{ value: 'all', label: '30 days' }, { value: '90', label: '90 days' }]} />
          </div>
        </Modal>
      </Section>
    </Page>
  );
}
