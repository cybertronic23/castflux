using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

namespace CastFluxLauncher
{
    internal static class Program
    {
        [STAThread]
        private static int Main()
        {
            string exeDir = AppDomain.CurrentDomain.BaseDirectory;
            string python = Path.Combine(exeDir, ".venv", "Scripts", "python.exe");
            string setup = Path.Combine(exeDir, "scripts", "setup_gui.bat");
            string ffmpegBin = Path.Combine(exeDir, "scripts", "ffmpeg", "bin");

            try
            {
                if (!File.Exists(python))
                {
                    if (!File.Exists(setup))
                    {
                        MessageBox.Show(
                            "CastFlux is missing scripts\\setup_gui.bat. Please extract the full portable package before running CastFlux.exe.",
                            "CastFlux",
                            MessageBoxButtons.OK,
                            MessageBoxIcon.Error);
                        return 1;
                    }

                    int setupCode = RunProcess(setup, "", exeDir, true);
                    if (setupCode != 0)
                    {
                        MessageBox.Show(
                            "CastFlux setup failed. Please check runtime\\logs in the CastFlux folder.",
                            "CastFlux",
                            MessageBoxButtons.OK,
                            MessageBoxIcon.Error);
                        return setupCode;
                    }
                }

                if (!File.Exists(python))
                {
                    MessageBox.Show(
                        "Python environment was not created. Please run scripts\\setup_gui.bat manually and check runtime\\logs.",
                        "CastFlux",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                    return 1;
                }

                string oldPath = Environment.GetEnvironmentVariable("PATH") ?? "";
                if (Directory.Exists(ffmpegBin))
                {
                    Environment.SetEnvironmentVariable("PATH", ffmpegBin + ";" + oldPath);
                }

                return RunProcess(python, "-m castflux.gui", exeDir, false);
            }
            catch (Exception ex)
            {
                MessageBox.Show(ex.Message, "CastFlux", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }

        private static int RunProcess(string fileName, string arguments, string workingDirectory, bool visible)
        {
            ProcessStartInfo startInfo = new ProcessStartInfo
            {
                FileName = fileName,
                Arguments = arguments,
                WorkingDirectory = workingDirectory,
                UseShellExecute = visible,
                CreateNoWindow = !visible
            };

            using (Process process = Process.Start(startInfo))
            {
                process.WaitForExit();
                return process.ExitCode;
            }
        }
    }
}
