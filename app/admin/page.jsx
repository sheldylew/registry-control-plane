import Link from 'next/link';

import { apiFetch } from '@/app/lib/server-api';

function formatRelativeTime(value) {
  const target = new Date(value);
  const diffMs = Date.now() - target.getTime();
  if (Number.isNaN(diffMs)) {
    return 'Unknown';
  }
  const diffMinutes = Math.floor(diffMs / (1000 * 60));
  if (diffMinutes < 1) {
    return 'Just now';
  }
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

function maxBucketValue(groups) {
  return Math.max(1, ...groups.flatMap((group) => group.map((bucket) => bucket.count)));
}

function TrendBars({ label, buckets, tone }) {
  const maxValue = Math.max(1, ...buckets.map((bucket) => bucket.count));
  const total = buckets.reduce((sum, bucket) => sum + bucket.count, 0);
  const midpoint = buckets[Math.floor(buckets.length / 2)];
  return (
    <div className='rounded-3xl border border-white/10 bg-slate-950/60 p-5'>
      <div className='flex items-center justify-between'>
        <p className='text-sm font-medium text-white'>{label}</p>
        <p className='text-xs uppercase tracking-[0.18em] text-slate-400'>{total} total</p>
      </div>
      <div className='mt-5 flex h-28 items-end gap-2'>
        {buckets.map((bucket) => (
          <div key={bucket.label} className='flex flex-1 flex-col items-center gap-2'>
            <div className='flex h-24 w-full items-end'>
              <div
                className={`w-full rounded-t-2xl transition-opacity ${tone} ${bucket.count === 0 ? 'opacity-30' : 'opacity-100'}`}
                style={{ height: bucket.count === 0 ? '4px' : `${Math.max(16, (bucket.count / maxValue) * 100)}%` }}
                title={`${bucket.label}: ${bucket.count}`}
              />
            </div>
            <span className='text-[10px] font-medium text-slate-500'>{bucket.count}</span>
          </div>
        ))}
      </div>
      <div className='mt-4 flex items-center justify-between text-[11px] uppercase tracking-[0.16em] text-slate-500'>
        <span>{buckets[0]?.label}</span>
        <span>{midpoint?.label}</span>
        <span>{buckets[buckets.length - 1]?.label}</span>
      </div>
    </div>
  );
}

export default async function AdminHomePage() {
  const response = await apiFetch('/api/admin/dashboard');
  let payload;

  try {
    payload = await response.json();
  } catch (error) {
    // Handle non-JSON responses (like HTML error pages)
    console.error('Failed to parse JSON response:', error);
    return (
      <div className='rounded-3xl border border-red-500/20 bg-red-950/20 p-8 text-center'>
        <h2 className='text-xl font-bold text-red-400'>Dashboard Error</h2>
        <p className='mt-2 text-red-300'>Failed to load dashboard data. The server returned an unexpected response.</p>
        <p className='mt-2 text-sm text-red-500'>Please check the server logs for more details.</p>
      </div>
    );
  }

  if (!response.ok) {
    return (
      <div className='rounded-3xl border border-red-500/20 bg-red-950/20 p-8 text-center'>
        <h2 className='text-xl font-bold text-red-400'>Dashboard Error</h2>
        <p className='mt-2 text-red-300'>{payload.detail || 'Failed to load dashboard data.'}</p>
      </div>
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
      <section className='grid gap-4 md:grid-cols-2 xl:grid-cols-5'>
        {stats.map((stat) => (
          <article key={stat.label} className={`rounded-3xl border border-white/10 bg-gradient-to-br ${stat.tone} p-6 shadow-lg shadow-slate-950/20`}>
            <p className='text-sm font-medium text-slate-300'>{stat.label}</p>
            <p className='mt-4 text-4xl font-semibold tracking-tight text-white'>{stat.value}</p>
            <p className='mt-3 text-sm leading-6 text-slate-400'>{stat.subvalue}</p>
          </article>
        ))}
      </section>

      <section className='grid gap-6 xl:grid-cols-[1.45fr_0.95fr]'>
        <article className='rounded-3xl border border-white/10 bg-slate-900/80 p-6'>
          <div className='flex items-center justify-between'>
            <div>
              <p className='text-sm font-medium uppercase tracking-[0.22em] text-cyan-300'>Provisioning trend</p>
              <h2 className='mt-3 text-2xl font-semibold text-white'>Identity and token velocity</h2>
            </div>
            <p className='text-sm text-slate-400'>
              Peak bucket: {maxBucketValue([payload.provisioning_trend.users, payload.provisioning_trend.tokens, payload.provisioning_trend.robots])}
            </p>
          </div>
          <div className='mt-6 grid gap-4 xl:grid-cols-3'>
            <TrendBars label='Users' buckets={payload.provisioning_trend.users} tone='bg-cyan-400/80' />
            <TrendBars label='Tokens' buckets={payload.provisioning_trend.tokens} tone='bg-emerald-400/80' />
            <TrendBars label='Robots' buckets={payload.provisioning_trend.robots} tone='bg-amber-300/80' />
          </div>
        </article>

        <article className='rounded-3xl border border-white/10 bg-slate-900/80 p-6'>
          <div className='flex items-center justify-between'>
            <div>
              <p className='text-sm font-medium uppercase tracking-[0.22em] text-cyan-300'>Registry mix</p>
              <h2 className='mt-3 text-2xl font-semibold text-white'>Largest repositories by tag count</h2>
            </div>
            <Link
              href='/repos'
              className='rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200 transition hover:border-cyan-400/40 hover:text-white'
            >
              Open browser
            </Link>
          </div>
          <div className='mt-6 space-y-4'>
            {payload.repo_distribution.length ? (
              payload.repo_distribution.map((repo, index) => {
                const maxTags = Math.max(1, ...payload.repo_distribution.map((item) => item.tag_count));
                const width = Math.max(12, (repo.tag_count / maxTags) * 100);
                return (
                  <div key={repo.name}>
                    <div className='flex items-center justify-between gap-4'>
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
              <p className='text-sm text-slate-300'>No registry repositories discovered yet.</p>
            )}
          </div>
        </article>
      </section>

      <section className='grid gap-6 xl:grid-cols-[1.2fr_0.8fr]'>
        <article className='rounded-3xl border border-white/10 bg-slate-900/80 p-6'>
          <div className='flex items-center justify-between'>
            <div>
              <p className='text-sm font-medium uppercase tracking-[0.22em] text-cyan-300'>Recent activity</p>
              <h2 className='mt-3 text-2xl font-semibold text-white'>Latest identity and credential events</h2>
            </div>
          </div>
          <div className='mt-6 space-y-4'>
            {payload.recent_activity.length ? (
              payload.recent_activity.map((event) => (
                <div key={`${event.type}-${event.timestamp}-${event.title}`} className='rounded-2xl border border-white/10 bg-slate-950/60 p-4'>
                  <div className='flex items-center justify-between gap-4'>
                    <p className='text-sm font-medium text-white'>{event.title}</p>
                    <p className='text-xs uppercase tracking-[0.18em] text-slate-500'>{formatRelativeTime(event.timestamp)}</p>
                  </div>
                  <p className='mt-2 text-sm text-slate-400'>{event.detail}</p>
                </div>
              ))
            ) : (
              <p className='text-sm text-slate-300'>No recent activity yet.</p>
            )}
          </div>
        </article>

        <article className='rounded-3xl border border-white/10 bg-slate-900/80 p-6'>
          <p className='text-sm font-medium uppercase tracking-[0.22em] text-cyan-300'>Quick links</p>
          <h2 className='mt-3 text-2xl font-semibold text-white'>Operator shortcuts</h2>
          <div className='mt-6 space-y-3'>
            <Link
              href='/admin/users'
              className='block rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-4 text-sm text-slate-200 transition hover:border-cyan-400/40 hover:text-white'
            >
              Manage users
            </Link>
            <Link
              href='/admin/tokens'
              className='block rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-4 text-sm text-slate-200 transition hover:border-cyan-400/40 hover:text-white'
            >
              Review PATs
            </Link>
            <Link
              href='/admin/robots'
              className='block rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-4 text-sm text-slate-200 transition hover:border-cyan-400/40 hover:text-white'
            >
              Review robots
            </Link>
            <Link
              href='/admin/audit'
              className='block rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-4 text-sm text-slate-200 transition hover:border-cyan-400/40 hover:text-white'
            >
              Inspect audit log
            </Link>
            <Link
              href='/admin/maintenance'
              className='block rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-4 text-sm text-slate-200 transition hover:border-cyan-400/40 hover:text-white'
            >
              Run maintenance
            </Link>
            <Link
              href='/repos'
              className='block rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-4 text-sm text-slate-200 transition hover:border-cyan-400/40 hover:text-white'
            >
              Browse registry
            </Link>
          </div>
        </article>
      </section>
    </div>
  );
}
