using Microsoft.Extensions.Hosting;

// ProcAI background monitoring service (transparent, stoppable, visible).
// The full hosted monitor (telemetry scan loop + alerting) is wired in during the
// service phase; this is the minimal host so the project compiles and runs.

var builder = Host.CreateApplicationBuilder(args);

// When the monitor worker is implemented it will be registered here, e.g.:
//   builder.Services.AddHostedService<MonitorWorker>();
//   builder.Services.AddWindowsService(o => o.ServiceName = "ProcAI Protection");

using var host = builder.Build();
await host.RunAsync();
