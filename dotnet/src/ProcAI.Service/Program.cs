using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using ProcAI.Service;

// ProcAI background monitoring service (transparent, stoppable, visible).
// Runs as a Windows Service when installed, or as a plain console for debugging.

var builder = Host.CreateApplicationBuilder(args);

builder.Services.AddHostedService<MonitorWorker>();
builder.Services.AddWindowsService(options => options.ServiceName = "ProcAI Protection");

using var host = builder.Build();
await host.RunAsync();
