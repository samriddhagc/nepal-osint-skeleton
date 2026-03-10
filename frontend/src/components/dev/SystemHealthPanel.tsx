import { useQuery } from '@tanstack/react-query'
import { Database, Server, Cpu, Layers, Clock, GitBranch, RefreshCw } from 'lucide-react'
import { fetchSystemStatus, type SystemStatus } from '../../api/system'

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    healthy: 'bg-emerald-400 shadow-emerald-400/50',
    degraded: 'bg-amber-400 shadow-amber-400/50',
    down: 'bg-red-400 shadow-red-400/50',
  }
  return (
    <span className={`w-2 h-2 rounded-full shadow-[0_0_6px] ${colors[status] || colors.down}`} />
  )
}

interface ServiceCardProps {
  name: string
  icon: React.ReactNode
  status: string
  metrics: Record<string, string | number>
}

function ServiceCard({ name, icon, status, metrics }: ServiceCardProps) {
  return (
    <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-4 hover:border-white/[0.12] transition-colors">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <div className="text-white/40">{icon}</div>
          <h3 className="text-sm font-medium text-white">{name}</h3>
        </div>
        <StatusDot status={status} />
      </div>
      <div className="space-y-2">
        {Object.entries(metrics).map(([key, value]) => (
          <div key={key} className="flex justify-between items-center text-xs">
            <span className="text-white/40">{key}</span>
            <span className="text-white font-mono tabular-nums">{value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function formatDuration(seconds: number): string {
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

export function SystemHealthPanel() {
  const { data: status, isLoading, refetch } = useQuery({
    queryKey: ['system-status'],
    queryFn: fetchSystemStatus,
    refetchInterval: 30000,
  })

  if (isLoading || !status) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-5 h-5 text-white/20 animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Service Grid */}
      <div className="grid grid-cols-4 gap-4">
        <ServiceCard
          name="PostgreSQL"
          icon={<Database size={16} />}
          status={status.database.status}
          metrics={{
            'Connections': `${status.database.active_connections}/${status.database.pool_size}`,
            'Waiting': String(status.database.waiting),
            'Latency': `${status.database.latency_ms}ms`,
          }}
        />
        <ServiceCard
          name="Redis"
          icon={<Server size={16} />}
          status={status.redis.status}
          metrics={{
            'Memory': status.redis.memory_used,
            'Peak': status.redis.memory_peak,
            'Clients': String(status.redis.connected_clients),
            'Keys': String(status.redis.keys),
          }}
        />
        <ServiceCard
          name="Scheduler"
          icon={<Cpu size={16} />}
          status={status.workers.status}
          metrics={{
            'Status': status.workers.scheduler_running ? 'Running' : 'Stopped',
            'Jobs': String(status.workers.registered_jobs),
            'Next Run': status.workers.next_run_in_seconds != null
              ? formatDuration(status.workers.next_run_in_seconds)
              : 'N/A',
          }}
        />
        <ServiceCard
          name="Job Groups"
          icon={<Layers size={16} />}
          status={status.queues.status}
          metrics={{
            'Ingestion': String(status.queues.ingestion_jobs),
            'Processing': String(status.queues.processing_jobs),
            'Realtime': String(status.queues.realtime_jobs),
          }}
        />
      </div>

      {/* Uptime & Version Bar */}
      <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-4">
        <div className="flex items-center gap-8 text-sm">
          <div className="flex items-center gap-2">
            <Clock size={14} className="text-white/30" />
            <span className="text-white/40">Uptime</span>
            <span className="text-white font-mono tabular-nums">{formatDuration(status.uptime_seconds)}</span>
          </div>
          <div className="flex items-center gap-2">
            <GitBranch size={14} className="text-white/30" />
            <span className="text-white/40">Version</span>
            <span className="text-white font-mono">{status.version}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-white/40">Environment</span>
            <span className={`px-2 py-0.5 rounded text-xs font-mono ${
              status.environment === 'production'
                ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
            }`}>
              {status.environment}
            </span>
          </div>
          <div className="flex-1" />
          <button
            onClick={() => refetch()}
            className="flex items-center gap-1.5 text-xs text-white/30 hover:text-white/60 transition-colors"
          >
            <RefreshCw size={12} />
            Refresh
          </button>
        </div>
      </div>
    </div>
  )
}
