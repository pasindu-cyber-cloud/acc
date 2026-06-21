using System.Net;
using System.Runtime.InteropServices;

namespace ProcAI.Core.Telemetry;

/// <summary>
/// Read-only Win32 interop for telemetry: per-process TCP connections (IP Helper)
/// and host memory status. ProcAI only *reads* data the OS already exposes; it
/// never injects, hooks, or modifies any process.
/// </summary>
internal static class NativeMethods
{
    // ---- IP Helper: per-process TCP table -------------------------------

    private const int AF_INET = 2;
    private const int TCP_TABLE_OWNER_PID_ALL = 5;
    private const int MIB_TCP_STATE_LISTEN = 2;

    [StructLayout(LayoutKind.Sequential)]
    private struct MIB_TCPROW_OWNER_PID
    {
        public uint state;
        public uint localAddr;
        public uint localPort;   // port is in the low 16 bits, network byte order
        public uint remoteAddr;
        public uint remotePort;
        public uint owningPid;
    }

    [DllImport("iphlpapi.dll", SetLastError = true)]
    private static extern uint GetExtendedTcpTable(
        IntPtr pTcpTable, ref int pdwSize, bool bOrder, int ulAf, int tableClass, uint reserved);

    /// <summary>A single owning-PID TCP connection.</summary>
    public readonly record struct TcpConnection(
        int Pid, int LocalPort, uint RemoteAddr, bool IsListening);

    /// <summary>Snapshot all IPv4 TCP connections with their owning PID.</summary>
    public static List<TcpConnection> GetTcpConnections()
    {
        var result = new List<TcpConnection>();
        int size = 0;
        // First call to get the required buffer size.
        GetExtendedTcpTable(IntPtr.Zero, ref size, true, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0);
        if (size <= 0) return result;

        IntPtr buffer = Marshal.AllocHGlobal(size);
        try
        {
            uint ret = GetExtendedTcpTable(buffer, ref size, true, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0);
            if (ret != 0) return result;

            int count = Marshal.ReadInt32(buffer);
            IntPtr rowPtr = buffer + 4;
            int rowSize = Marshal.SizeOf<MIB_TCPROW_OWNER_PID>();
            for (int i = 0; i < count; i++)
            {
                var row = Marshal.PtrToStructure<MIB_TCPROW_OWNER_PID>(rowPtr);
                result.Add(new TcpConnection(
                    Pid: (int)row.owningPid,
                    LocalPort: NetworkPort(row.localPort),
                    RemoteAddr: row.remoteAddr,
                    IsListening: row.state == MIB_TCP_STATE_LISTEN));
                rowPtr += rowSize;
            }
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
        return result;
    }

    private static int NetworkPort(uint raw) =>
        ((int)(raw & 0xFF) << 8) | (int)((raw >> 8) & 0xFF);

    // ---- Host memory ----------------------------------------------------

    [StructLayout(LayoutKind.Sequential)]
    private sealed class MEMORYSTATUSEX
    {
        public uint dwLength = (uint)Marshal.SizeOf<MEMORYSTATUSEX>();
        public uint dwMemoryLoad;
        public ulong ullTotalPhys;
        public ulong ullAvailPhys;
        public ulong ullTotalPageFile;
        public ulong ullAvailPageFile;
        public ulong ullTotalVirtual;
        public ulong ullAvailVirtual;
        public ulong ullAvailExtendedVirtual;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GlobalMemoryStatusEx([In, Out] MEMORYSTATUSEX lpBuffer);

    /// <summary>(totalPhysicalBytes, memoryLoadPercent). Zero on failure.</summary>
    public static (ulong TotalPhys, uint LoadPercent) GetMemoryStatus()
    {
        var status = new MEMORYSTATUSEX();
        return GlobalMemoryStatusEx(status)
            ? (status.ullTotalPhys, status.dwMemoryLoad)
            : (0UL, 0U);
    }
}
