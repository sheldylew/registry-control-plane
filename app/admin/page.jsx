import Link from 'next/link';

import Alert from '@/app/components/ui/alert';
import Badge from '@/app/components/ui/badge';
import Button from '@/app/components/ui/button';
import EmptyState from '@/app/components/ui/empty-state';
import { MobileCollapsiblePanel, Panel, PanelHeader } from '@/app/components/ui/panel';
import StatCard from '@/app/components/ui/stat-card';
import { MobileDisclosureCard, MobileField } from '@/app/components/ui/table';
import { formatRelativeTime } from '@/app/lib/date-format';
import { apiFetch } from '@/app/lib/server-api';
import { getUiTimezone } from '@/app/lib/ui-settings';

function maxBucketValue(groups) {
  return Math.max(1, ...groups.flatMap((group) => group.map((bucket) => bucket.count)));
}

function TrendBars({ label, buckets, tone }) {
  const maxValue = Math.max(1, ...buckets.map((bucket) => bucket.count));
  const total = buckets.reduce((sum, bucket) => sum + bucket.count, 0);
  const midpoint = buckets[Math.floor(buckets.length / 2)];
  return (
    <div className='rounded-lg border border-white/10 bg-slate-950/60 p-4 sm:p-5'>
      <div className='flex items-center justify-between'>
        <p className='text-sm font-medium text-white'>{label}</p>
        <p className='text-xs uppercase tracking-[0.18em] text-slate-400'>{total} total</p>
      </div>
      <div className='mt-4 flex h-24 items-end gap-1.5 sm:mt-5 sm:h-28 sm:gap-2'>
        {buckets.map((bucket) => (
          <div key={bucket.label} className='flex flex-1 flex-col items-center gap-2'>
            <div className='flex h-20 w-full items-end sm:h-24'>
              <div
                className={`w-full rounded-t-md transition-opacity ${tone} ${bucket.count === 0 ? 'opacity-30' : 'opacity-100'}`}
                style={{ height: bucket.count === 0 ? '4px' : `${Math.max(16, (bucket.count / maxValue) * 100)}%` }}
                title={`${bucket.label}: ${bucket.count}`}
              />
            </div>
            <span className='text-[10px] font-medium text-slate-500'>{bucket.count}</span>
          </div>
        ))}
      </div>
      <div className='mt-3 flex items-center justify-between text-[10px] uppercase tracking-[0.16em] text-slate-500 sm:mt-4 sm:text-[11px]'>
        <span>{buckets[0]?.label}</span>
        <span>{midpoint?.label}</span>
        <span>{buckets[buckets.length - 1]?.label}</span>
      </div>
    </div>
  );
}

export default async function AdminHomePage() {
  const timeZone = await getUiTimezone();
  const response = await apiFetch('/api/admin/dashboard');
  let payload;

  try {
    payload = await response.json();
  } catch (error) {
    // Handle non-JSON responses (like HTML error pages)
    console.error('Failed to parse JSON response:', error);
    return (
      <Alert tone="rose" className='p-8 text-center'>
        <h2 className='text-xl font-bold text-red-400'>Dashboard Error</h2>
        <p className='mt-2 text-red-300'>Failed to load dashboard data. The server returned an unexpected response.</p>
        <p className='mt-2 text-sm text-red-500'>Please check the server logs for more details.</p>
      </Alert>
    );
  }

  if (!response.ok) {
    return (
      <Alert tone="rose" className='p-8 text-center'>
        <h2 className='text-xl font-bold text-red-400'>Dashboard Error</h2>
        <p className='mt-2 text-red-300'>{payload.detail || 'Failed to load dashboard data.'}</p>
      </Alert>
    );
  }

  const stats = [
    {
      label: 'Active users',
      value: payload.stats.users_active,
      subvalue: `${payload.stats.users_total} total identities`,
      tone: 'from-cyan-400/25 to-cyan-500/5',
    },
    {
      label: 'Active PATs',
      value: payload.stats.pats_active,
      subvalue: 'CLI credentials currently valid',
      tone: 'from-emerald-400/25 to-emerald-500/5',
    },
    {
      label: 'Active robots',
      value: payload.stats.robots_active,
      subvalue: 'Automation identities online',
      tone: 'from-amber-300/20 to-amber-500/5',
    },
    {
      label: 'Registry repos',
      value: payload.stats.registry_repositories,
      subvalue: `${payload.stats.registry_tags} tags discovered`,
      tone: 'from-fuchsia-400/20 to-fuchsia-500/5',
    },
    {
      label: 'Public pulls',
      value: payload.stats.public_pull_tokens_issued,
      subvalue: 'Anonymous public pull tokens granted',
      tone: 'from-sky-300/20 to-sky-500/5',
    },
  ];

  return (
    <div className='space-y-6'>
      <Panel as="section" className='p-4 sm:p-6'>
        <PanelHeader
          eyebrow="Overview"
          title="Control-plane snapshot"
          description="At-a-glance identity, credential, and registry counts for the current control plane."
        />
        <div className='mt-5 grid gap-3 sm:mt-6 sm:gap-4 md:grid-cols-2 xl:grid-cols-5'>
          {stats.map((stat) => (
            <StatCard
              key={stat.label}
              label={stat.label}
              value={stat.value}
              detail={stat.subvalue}
              tone={stat.label === 'Active users' ? 'cyan' : stat.label === 'Active PATs' ? 'emerald' : stat.label === 'Active robots' ? 'amber' : 'slate'}
            />
          ))}
        </div>
      </Panel>

      <section className='grid gap-6 xl:grid-cols-[1.45fr_0.95fr]'>
        <Panel as="article" className='p-4 sm:p-6'>
          <PanelHeader
            eyebrow="Provisioning trend"
            title="Identity and token velocity"
            action={<Badge>Peak bucket: {maxBucketValue([payload.provisioning_trend.users, payload.provisioning_trend.tokens, payload.provisioning_trend.robots])}</Badge>}
          />
          <div className='mt-5 grid gap-3 sm:mt-6 sm:gap-4 xl:grid-cols-3'>
            <TrendBars label='Users' buckets={payload.provisioning_trend.users} tone='bg-cyan-400/80' />
            <TrendBars label='Tokens' buckets={payload.provisioning_trend.tokens} tone='bg-emerald-400/80' />
            <TrendBars label='Robots' buckets={payload.provisioning_trend.robots} tone='bg-amber-300/80' />
          </div>
        </Panel>

        <Panel as="article" className='p-4 sm:p-6'>
          <PanelHeader
            eyebrow="Registry mix"
            title="Largest repositories by tag count"
            action={(
            <Button
              as={Link}
              href='/repos'
              prefetch={false}
              variant="secondary"
              className="w-full sm:w-auto"
            >
              Open browser
            </Button>
            )}
          />
          <div className='mt-5 space-y-4 sm:mt-6'>
            {payload.repo_distribution.length ? (
              payload.repo_distribution.map((repo, index) => {
                const maxTags = Math.max(1, ...payload.repo_distribution.map((item) => item.tag_count));
                const width = Math.max(12, (repo.tag_count / maxTags) * 100);
                return (
                  <div key={repo.name}>
                    <div className='flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-4'>
                      <p className='truncate text-sm font-medium text-white'>{repo.name}</p>
                      <p className='text-sm text-slate-400'>{repo.tag_count} tags</p>
                    </div>
                    <div className='mt-2 h-3 rounded-full bg-slate-950/80'>
                      <div
                        className={`h-3 rounded-full ${index % 2 === 0 ? 'bg-cyan-400/80' : 'bg-emerald-400/80'}`}
                        style={{ width: `${width}%` }}
                      />
                    </div>
                  </div>
                );
              })
            ) : (
              <EmptyState title="No repositories discovered" description="No registry repositories discovered yet." />
            )}
          </div>
        </Panel>
      </section>

      <section className='grid gap-6 xl:grid-cols-[1.2fr_0.8fr]'>
        <MobileCollapsiblePanel
          as="article"
          className='p-4 sm:p-6'
          eyebrow="Recent activity"
          title="Latest identity and credential events"
          summaryMeta={`${payload.recent_activity.length} events`}
        >
          <PanelHeader eyebrow="Recent activity" title="Latest identity and credential events" />
          <div className='mt-6 space-y-4'>
            {payload.recent_activity.length ? (
              payload.recent_activity.map((event) => (
              <div key={`${event.type}-${event.timestamp}-${event.title}`}>
                <MobileDisclosureCard
                  className="lg:hidden"
                  summary={(
                    <div>
                      <p className='text-sm font-medium text-white'>{event.title}</p>
                      <p className='mt-1 text-xs uppercase tracking-[0.18em] text-slate-500'>{formatRelativeTime(event.timestamp, { timeZone })}</p>
                    </div>
                  )}
                >
                  <MobileField label="Details">{event.detail}</MobileField>
                </MobileDisclosureCard>
              <div className='hidden rounded-lg border border-white/10 bg-slate-950/60 p-4 lg:block'>
                  <div className='flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-4'>
                    <p className='text-sm font-medium text-white'>{event.title}</p>
                    <p className='text-xs uppercase tracking-[0.18em] text-slate-500'>{formatRelativeTime(event.timestamp, { timeZone })}</p>
                  </div>
                  <p className='mt-2 text-sm text-slate-400'>{event.detail}</p>
                </div>
                </div>
              ))
            ) : (
              <EmptyState title="No recent activity" description="No recent activity yet." />
            )}
          </div>
        </MobileCollapsiblePanel>

        <Panel as="article" className='p-4 sm:p-6'>
          <PanelHeader eyebrow="Quick links" title="Operator shortcuts" />
          <div className='mt-6 space-y-3'>
            {[
              ['/admin/users', 'Manage users'],
              ['/admin/tokens', 'Review PATs'],
              ['/admin/robots', 'Review robots'],
              ['/admin/audit', 'Inspect audit log'],
              ['/admin/maintenance', 'Run maintenance'],
              ['/repos', 'Browse registry'],
            ].map(([href, label]) => (
              <Link
                key={href}
                href={href}
                prefetch={false}
              className='block rounded-lg border border-white/10 bg-slate-950/60 px-4 py-3 text-sm text-slate-200 transition hover:border-cyan-400/40 hover:text-white sm:py-4'
              >
                {label}
              </Link>
            ))}
          </div>
        </Panel>
      </section>
    </div>
  );
}
