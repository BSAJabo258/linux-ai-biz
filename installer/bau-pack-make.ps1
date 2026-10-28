<#
BAU Pack maker (Windows). Run it on a computer with internet: it fills a USB stick you pick
with the BAU laptop's local AI models, each checked against its pinned SHA-256, and your
locked keys file (BAU-KEYS.enc) if it sits next to this script. It never formats or erases
anything; it only writes into a BAU-PACK folder on the stick. No Python needed.

Easiest: double-click BAU-Pack-Make.cmd, or:

    powershell -ExecutionPolicy Bypass -File .\bau-pack-make.ps1

Then plug the stick into the BAU laptop and run: sudo bau pack install
docs/PACK.md explains every step.
#>
param(
    [string]$Target = "",
    [string]$Manifest = "",
    [switch]$Yes
)

# The same files, links and hashes as src/bau/data/registry_defaults.yaml (a test checks).
$BauModels = @(
    @{ Id = "qwen3.5-9b"; File = "Qwen3.5-9B-Q4_K_M.gguf"; Url = "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf"; Size = 5680522464; Sha256 = "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8"; Role = "the desktop boss: runs on the NVIDIA card (docs/DESKTOP.md)" },
    @{ Id = "qwen3.5-9b-mtp"; File = "Qwen3.5-9B-MTP-Q4_K_M.gguf"; Url = "https://huggingface.co/unsloth/Qwen3.5-9B-MTP-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf"; Size = 5868826976; Sha256 = "e8dd94817e95d6c0939102049d068418269978377b13616c4726235e232841fe"; Role = "the 9B with its own draft head, to measure on the card (docs/GPU.md)" },
    @{ Id = "qwen3.5-4b"; File = "Qwen3.5-4B-Q4_K_M.gguf"; Url = "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf"; Size = 2740937888; Sha256 = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"; Role = "the boss: runs Jarvis and the agents" },
    @{ Id = "qwen3-4b-heretic-content"; File = "Qwen3-4B-Instruct-2507-heretic.Q4_K_M.gguf"; Url = "https://huggingface.co/mradermacher/Qwen3-4B-Instruct-2507-heretic-GGUF/resolve/main/Qwen3-4B-Instruct-2507-heretic.Q4_K_M.gguf"; Size = 2497279584; Sha256 = "5d38e532cf33a5b56760bc7803aaabffb240d0604f1e389e4db148830c2bb747"; Role = "the thinker: uncensored ideas, sealed" },
    @{ Id = "qwen2.5-1.5b-instruct"; File = "qwen2.5-1.5b-instruct-q4_k_m.gguf"; Url = "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"; Size = 1117320736; Sha256 = "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"; Role = "the backup: small and fast" }
)

# The Wi-Fi programs the first stick image left out (the laptop needs them to join any
# Wi-Fi network). Debian trixie amd64; same list as src/bau/pack.py (a test checks).
$BauDebs = @(
    @{ Name = "iw"; File = "iw_6.9-1_amd64.deb"; Pool = "pool/main/i/iw/iw_6.9-1_amd64.deb"; Size = 106300; Sha256 = "61c0848fe4c98718f1f1ad7526ae4858d91f85e3139f0e723bed4bc2aa729422" },
    @{ Name = "libnl-3-200"; File = "libnl-3-200_3.7.0-2_amd64.deb"; Pool = "pool/main/libn/libnl3/libnl-3-200_3.7.0-2_amd64.deb"; Size = 59432; Sha256 = "ce5c153953016be42def7b105f37d55eae07a9608d1dfe6bcb03cc017fc384cb" },
    @{ Name = "libnl-genl-3-200"; File = "libnl-genl-3-200_3.7.0-2_amd64.deb"; Pool = "pool/main/libn/libnl3/libnl-genl-3-200_3.7.0-2_amd64.deb"; Size = 18136; Sha256 = "8f2f81ef4c6f8636f0b0cb2ff40b3c54a497d121f49c485620ae43c94782cd94" },
    @{ Name = "libnl-route-3-200"; File = "libnl-route-3-200_3.7.0-2_amd64.deb"; Pool = "pool/main/libn/libnl3/libnl-route-3-200_3.7.0-2_amd64.deb"; Size = 181704; Sha256 = "1c8c95542688996cff8e954583642b10a3bd78b69954f565fda62144c2bc3897" },
    @{ Name = "libpcsclite1"; File = "libpcsclite1_2.3.3-1_amd64.deb"; Pool = "pool/main/p/pcsc-lite/libpcsclite1_2.3.3-1_amd64.deb"; Size = 55248; Sha256 = "a8bc4725549060d1e696d358e32a3699d947d5381871553a290389830bebccbd" },
    @{ Name = "wireless-regdb"; File = "wireless-regdb_2026.05.30-1~deb13u1_all.deb"; Pool = "pool/main/w/wireless-regdb/wireless-regdb_2026.05.30-1~deb13u1_all.deb"; Size = 12400; Sha256 = "72048ee2f369a8c2df8b5f99f79489d3812d869282038cfe55e23a4748231399" },
    @{ Name = "wpasupplicant"; File = "wpasupplicant_2.10-24_amd64.deb"; Pool = "pool/main/w/wpa/wpasupplicant_2.10-24_amd64.deb"; Size = 1426452; Sha256 = "99f50410baddebd421497703ad9b6d0e05deb3dfda99a96b2814f630d9b84498" }
)
$BauDebMirrors = @("https://deb.debian.org/debian/", "https://snapshot.debian.org/archive/debian/20261018T000000Z/")
# The desktop's NVIDIA driver without the internet (docs/DESKTOP.md step 4): Debian 13's
# driver 550.163.01 and everything it needs to build for the stick's kernel 6.12.113. Resolved
# 2026-10-28 with apt on the stick's own system (live-v0.1.0-76bc200) and installed from these
# files with the network off: dkms built nvidia-current and signed it. bau-gpu-setup carries
# the same SHA-256 list and checks every file before installing.
$BauNvidiaKernel = "6.12.113+deb13-amd64"
$BauNvidiaDebs = @(
    @{ Name = "linux-headers-6.12.113+deb13-common"; File = "linux-headers-6.12.113+deb13-common_6.12.113-1_all.deb"; Archive = "debian-security"; Pool = "pool/updates/main/l/linux/linux-headers-6.12.113%2bdeb13-common_6.12.113-1_all.deb"; Size = 11326108; Sha256 = "fa8f7b1eaa63d5c87141c9244131b5ae56f92272ee2971dfe22a81442a15ae5d" },
    @{ Name = "linux-kbuild-6.12.113+deb13"; File = "linux-kbuild-6.12.113+deb13_6.12.113-1_amd64.deb"; Archive = "debian-security"; Pool = "pool/updates/main/l/linux/linux-kbuild-6.12.113%2bdeb13_6.12.113-1_amd64.deb"; Size = 1899400; Sha256 = "f7a65a8f794fc2cd70e35749e212da654bc5157ea525f7bf67412f417cd5d0c9" },
    @{ Name = "linux-headers-6.12.113+deb13-amd64"; File = "linux-headers-6.12.113+deb13-amd64_6.12.113-1_amd64.deb"; Archive = "debian-security"; Pool = "pool/updates/main/l/linux/linux-headers-6.12.113%2bdeb13-amd64_6.12.113-1_amd64.deb"; Size = 3225196; Sha256 = "99762af0e483c3309d3ab12bc755d017c7f4c4d126725b4d41a03c6cb95f88b3" },
    @{ Name = "update-glx"; File = "update-glx_1.2.2_amd64.deb"; Archive = "debian"; Pool = "pool/contrib/g/glx-alternatives/update-glx_1.2.2_amd64.deb"; Size = 5432; Sha256 = "9803ce7e35738b8416b223d5c142c2d45545041b22729ae984e0e2cbe6e14db1" },
    @{ Name = "glx-alternative-mesa"; File = "glx-alternative-mesa_1.2.2_amd64.deb"; Archive = "debian"; Pool = "pool/contrib/g/glx-alternatives/glx-alternative-mesa_1.2.2_amd64.deb"; Size = 4760; Sha256 = "a72c331f3bd6b2acb4fa75428af4a7ce37e23a0f333e5bf34c05da77fbc1a5e1" },
    @{ Name = "nvidia-installer-cleanup"; File = "nvidia-installer-cleanup_20240109+1_amd64.deb"; Archive = "debian"; Pool = "pool/contrib/n/nvidia-support/nvidia-installer-cleanup_20240109%2b1_amd64.deb"; Size = 13924; Sha256 = "b095e1b688f0a648b1b3403b3e20264000b3ccf09e30fad97b45abdc4e2c4347" },
    @{ Name = "glx-diversions"; File = "glx-diversions_1.2.2_amd64.deb"; Archive = "debian"; Pool = "pool/contrib/g/glx-alternatives/glx-diversions_1.2.2_amd64.deb"; Size = 7408; Sha256 = "7548ef0f58d2ff3ac1ecdb019c6581caf9ee9ea5e2eb23e7f5195e6aa8dff165" },
    @{ Name = "glx-alternative-nvidia"; File = "glx-alternative-nvidia_1.2.2_amd64.deb"; Archive = "debian"; Pool = "pool/contrib/g/glx-alternatives/glx-alternative-nvidia_1.2.2_amd64.deb"; Size = 5776; Sha256 = "843665145b3a76260ae715567bbabca209f08a98420e33a1abdcf49992060f21" },
    @{ Name = "nvidia-legacy-check"; File = "nvidia-legacy-check_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/nvidia-legacy-check_550.163.01-2_amd64.deb"; Size = 167384; Sha256 = "046170d65cad8fbe1babdc18261ace399fde3597378c617b5a3bd8ed0d10951c" },
    @{ Name = "nvidia-alternative"; File = "nvidia-alternative_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/nvidia-alternative_550.163.01-2_amd64.deb"; Size = 163604; Sha256 = "39ec2e4872ec620cccac54dd7162834ce3ee2e77bf5c1d38e2dab32467c2b050" },
    @{ Name = "libnvidia-glvkspirv"; File = "libnvidia-glvkspirv_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/libnvidia-glvkspirv_550.163.01-2_amd64.deb"; Size = 3208972; Sha256 = "f2b89aa2c51c0ff52c647e6466c3911f33664c2fecb0c9dc0c69580690725e41" },
    @{ Name = "libnvidia-gpucomp"; File = "libnvidia-gpucomp_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/libnvidia-gpucomp_550.163.01-2_amd64.deb"; Size = 11842160; Sha256 = "f058804c64345d205e9350d31584bff1e60494a97b7a9af3c486513998d46ec2" },
    @{ Name = "libnvidia-eglcore"; File = "libnvidia-eglcore_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/libnvidia-eglcore_550.163.01-2_amd64.deb"; Size = 7803320; Sha256 = "15e5dd1929a6ef0ec3434318259221c0494e060b9fda131fa353d03a1f310bfb" },
    @{ Name = "libnvidia-glcore"; File = "libnvidia-glcore_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/libnvidia-glcore_550.163.01-2_amd64.deb"; Size = 8105100; Sha256 = "d0ddaeb5aa552757e6423cad2fa4829f10dd8b771688d84fae19f799d094e983" },
    @{ Name = "libglx-nvidia0"; File = "libglx-nvidia0_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/libglx-nvidia0_550.163.01-2_amd64.deb"; Size = 400548; Sha256 = "79d35284eef1a06431b78b806403e6b4373dfac09540a085f2764ceccc1c9199" },
    @{ Name = "libgl1-nvidia-glvnd-glx"; File = "libgl1-nvidia-glvnd-glx_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/libgl1-nvidia-glvnd-glx_550.163.01-2_amd64.deb"; Size = 344628; Sha256 = "a7a3db2620c022e90e8b5d1e367b8bafbe8c1ad5017abdc6bc90c47000967811" },
    @{ Name = "nvidia-egl-common"; File = "nvidia-egl-common_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/nvidia-egl-common_550.163.01-2_amd64.deb"; Size = 161616; Sha256 = "9ff6897c2b6b936966bfb0ba63e987a9aa3d22c5eeaf98365dc18b127cc6afc0" },
    @{ Name = "libnvidia-egl-wayland1"; File = "libnvidia-egl-wayland1_1%3a1.1.18-1_amd64.deb"; Archive = "debian"; Pool = "pool/main/e/egl-wayland/libnvidia-egl-wayland1_1.1.18-1_amd64.deb"; Size = 32068; Sha256 = "24d34b57e07b5cc3bb9ca174d6101e007430c4a413bfa607178f9ccceac92877" },
    @{ Name = "libegl-nvidia0"; File = "libegl-nvidia0_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/libegl-nvidia0_550.163.01-2_amd64.deb"; Size = 429156; Sha256 = "e6a491ba403d9cf106c66cd3c3a75c7301578a64db5fe989c93e25e740412656" },
    @{ Name = "nvidia-egl-icd"; File = "nvidia-egl-icd_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/nvidia-egl-icd_550.163.01-2_amd64.deb"; Size = 161340; Sha256 = "014f9958e712bcc519335c23ce42ed75cc33648cb94497e400c792c761dd6e37" },
    @{ Name = "nvidia-driver-libs"; File = "nvidia-driver-libs_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/nvidia-driver-libs_550.163.01-2_amd64.deb"; Size = 161676; Sha256 = "2974212d6be2d74824d414645b85dcafc71556d1a3b28524851c84db1a4727ed" },
    @{ Name = "libnvidia-ml1"; File = "libnvidia-ml1_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/libnvidia-ml1_550.163.01-2_amd64.deb"; Size = 727044; Sha256 = "01c1b67d511d7f52c6aa60e14ed56a8eb725d5dc85784a08214d6cb0f4fd1f89" },
    @{ Name = "nvidia-driver-bin"; File = "nvidia-driver-bin_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/nvidia-driver-bin_550.163.01-2_amd64.deb"; Size = 229032; Sha256 = "de9051d74584c8f93bd320fa1cfddfe91d55de45d94e076a4ec99b36aecf7574" },
    @{ Name = "nvidia-support"; File = "nvidia-support_20240109+1_amd64.deb"; Archive = "debian"; Pool = "pool/contrib/n/nvidia-support/nvidia-support_20240109%2b1_amd64.deb"; Size = 14788; Sha256 = "5523a2b2230f6ea46c35442a4a750dd35338a38ec56ba7afb53571ae36266e3d" },
    @{ Name = "xserver-xorg-video-nvidia"; File = "xserver-xorg-video-nvidia_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/xserver-xorg-video-nvidia_550.163.01-2_amd64.deb"; Size = 2337672; Sha256 = "e610838d217e690c29eda630193aa4a2d2d45ef663e3f527c6efe16df06c0d71" },
    @{ Name = "nvidia-vdpau-driver"; File = "nvidia-vdpau-driver_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/nvidia-vdpau-driver_550.163.01-2_amd64.deb"; Size = 657264; Sha256 = "bd22a89a993cdcf5528a956681ce070c43112924b0ff91de360efcf6ecf7b18c" },
    @{ Name = "firmware-nvidia-gsp"; File = "firmware-nvidia-gsp_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free-firmware/n/nvidia-graphics-drivers/firmware-nvidia-gsp_550.163.01-2_amd64.deb"; Size = 37155068; Sha256 = "e07e243f33cf7066737e3f556f3325a5e57199a9549a93f2158eec3921ea0beb" },
    @{ Name = "nvidia-kernel-common"; File = "nvidia-kernel-common_20240109+1_amd64.deb"; Archive = "debian"; Pool = "pool/contrib/n/nvidia-support/nvidia-kernel-common_20240109%2b1_amd64.deb"; Size = 4572; Sha256 = "18b0c696ea7b8ac1f4725b89b0dab662b587a253ef730b8c2c5ca3911d5cb920" },
    @{ Name = "nvidia-modprobe"; File = "nvidia-modprobe_570.133.07-1_amd64.deb"; Archive = "debian"; Pool = "pool/contrib/n/nvidia-modprobe/nvidia-modprobe_570.133.07-1_amd64.deb"; Size = 21704; Sha256 = "86258a704cbac1d2a064679140c9494e5585ce6bf56febb7a77939e3e06c7ec8" },
    @{ Name = "nvidia-kernel-support"; File = "nvidia-kernel-support_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/nvidia-kernel-support_550.163.01-2_amd64.deb"; Size = 162596; Sha256 = "e6c652d5a006e08855e602f7b45a4d5f3c2f5199acc1918c6da7fb6c144739dd" },
    @{ Name = "libdpkg-perl"; File = "libdpkg-perl_1.22.22_all.deb"; Archive = "debian"; Pool = "pool/main/d/dpkg/libdpkg-perl_1.22.22_all.deb"; Size = 650808; Sha256 = "b41eaeb4879091023f8c1a058510844a244d3d0bd0f437e0e05d58213e36fd9f" },
    @{ Name = "bzip2"; File = "bzip2_1.0.8-6_amd64.deb"; Archive = "debian"; Pool = "pool/main/b/bzip2/bzip2_1.0.8-6_amd64.deb"; Size = 40520; Sha256 = "6b5fbe71f0fc41e85919bc4b3c514e6c47577c5005dbf1f5af6e4a49cc221aab" },
    @{ Name = "patch"; File = "patch_2.8-2_amd64.deb"; Archive = "debian"; Pool = "pool/main/p/patch/patch_2.8-2_amd64.deb"; Size = 134328; Sha256 = "80c46a0085b33acc74bf451fddb6a70cb43d4ebcc4a873aec04d8d0a63ffc630" },
    @{ Name = "make"; File = "make_4.4.1-2_amd64.deb"; Archive = "debian"; Pool = "pool/main/m/make-dfsg/make_4.4.1-2_amd64.deb"; Size = 463104; Sha256 = "70a9709e665383b06068ccd423d62ea191b65355f318a25565dbf324b254cec6" },
    @{ Name = "libsframe1"; File = "libsframe1_2.44-3_amd64.deb"; Archive = "debian"; Pool = "pool/main/b/binutils/libsframe1_2.44-3_amd64.deb"; Size = 78360; Sha256 = "38f625dfdc582717029ac3a3e97c51d994ec2e7a0e9b230c6b44e40d1276311f" },
    @{ Name = "binutils-common"; File = "binutils-common_2.44-3_amd64.deb"; Archive = "debian"; Pool = "pool/main/b/binutils/binutils-common_2.44-3_amd64.deb"; Size = 2508768; Sha256 = "002da5d23f8757dee97a2c0a40e0e1d4d85a43da094488ee2ee7068d4d3691f9" },
    @{ Name = "libbinutils"; File = "libbinutils_2.44-3_amd64.deb"; Archive = "debian"; Pool = "pool/main/b/binutils/libbinutils_2.44-3_amd64.deb"; Size = 534440; Sha256 = "4f4664c8a8f0ad0c8631c39fab02e3d8d86ccc6f4436a1d59f059dbcb0492679" },
    @{ Name = "libgprofng0"; File = "libgprofng0_2.44-3_amd64.deb"; Archive = "debian"; Pool = "pool/main/b/binutils/libgprofng0_2.44-3_amd64.deb"; Size = 807764; Sha256 = "0d36d0bde85c467ac6735dded08e19dd30ae1369e3908b9eb48ccc0d6ff66648" },
    @{ Name = "libctf-nobfd0"; File = "libctf-nobfd0_2.44-3_amd64.deb"; Archive = "debian"; Pool = "pool/main/b/binutils/libctf-nobfd0_2.44-3_amd64.deb"; Size = 155672; Sha256 = "e280b2be3db6e584500e865c251605b95c346767d87ccb2524e44992048fc657" },
    @{ Name = "libctf0"; File = "libctf0_2.44-3_amd64.deb"; Archive = "debian"; Pool = "pool/main/b/binutils/libctf0_2.44-3_amd64.deb"; Size = 88616; Sha256 = "120cafcd93132a276fa92a8fb4cf39b23d14e5a3e348f4f5580638d71ca95ac5" },
    @{ Name = "binutils-x86-64-linux-gnu"; File = "binutils-x86-64-linux-gnu_2.44-3_amd64.deb"; Archive = "debian"; Pool = "pool/main/b/binutils/binutils-x86-64-linux-gnu_2.44-3_amd64.deb"; Size = 1013844; Sha256 = "e6741ce95ff0f7a131c8d9faa3528ccbbc453078bbc62a97da81340ed7462c53" },
    @{ Name = "binutils"; File = "binutils_2.44-3_amd64.deb"; Archive = "debian"; Pool = "pool/main/b/binutils/binutils_2.44-3_amd64.deb"; Size = 265400; Sha256 = "6bc08c02539ba53b5e748142397144c499f9b20b5fa9bb56431545db124addeb" },
    @{ Name = "dpkg-dev"; File = "dpkg-dev_1.22.22_all.deb"; Archive = "debian"; Pool = "pool/main/d/dpkg/dpkg-dev_1.22.22_all.deb"; Size = 1337268; Sha256 = "6d4020421740a70e1fb9c41b07f8bb8306d93aef6fea1a8ce11a1f839921f414" },
    @{ Name = "dkms"; File = "dkms_3.2.2-1~deb13u1_all.deb"; Archive = "debian"; Pool = "pool/main/d/dkms/dkms_3.2.2-1~deb13u1_all.deb"; Size = 60084; Sha256 = "6840d049df96419be706d135bcba4355e08864b0794977a616db16330871d412" },
    @{ Name = "nvidia-kernel-dkms"; File = "nvidia-kernel-dkms_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/nvidia-kernel-dkms_550.163.01-2_amd64.deb"; Size = 41721692; Sha256 = "729d17210de2a407c27b33d1811a72502483d189251dafd718e453b0c4e40107" },
    @{ Name = "nvidia-driver"; File = "nvidia-driver_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/nvidia-driver_550.163.01-2_amd64.deb"; Size = 530592; Sha256 = "198033cf94ebf7d6428f231bad3020342fe353ff0d56665414a7318277b9af79" },
    @{ Name = "libcc1-0"; File = "libcc1-0_14.2.0-19_amd64.deb"; Archive = "debian"; Pool = "pool/main/g/gcc-14/libcc1-0_14.2.0-19_amd64.deb"; Size = 42796; Sha256 = "2d587e3bfba4aec701946b7ba0c1640b97b6d8dd0a34ba1c70ae85261ecedefa" },
    @{ Name = "libitm1"; File = "libitm1_14.2.0-19_amd64.deb"; Archive = "debian"; Pool = "pool/main/g/gcc-14/libitm1_14.2.0-19_amd64.deb"; Size = 25956; Sha256 = "febdb3c528cde1a3abe952e17a1d3cfa7ccaca5b6f506d983d34385dad199490" },
    @{ Name = "libasan8"; File = "libasan8_14.2.0-19_amd64.deb"; Archive = "debian"; Pool = "pool/main/g/gcc-14/libasan8_14.2.0-19_amd64.deb"; Size = 2725272; Sha256 = "771899ade7310fe31aa538a509354c33d62bbe4e408b4e5fc1e513988dc42645" },
    @{ Name = "liblsan0"; File = "liblsan0_14.2.0-19_amd64.deb"; Archive = "debian"; Pool = "pool/main/g/gcc-14/liblsan0_14.2.0-19_amd64.deb"; Size = 1204164; Sha256 = "a0df07da76287a45e665d584363dc2a6a1c4e240aee41b8bbc0f67cdff97cd68" },
    @{ Name = "libtsan2"; File = "libtsan2_14.2.0-19_amd64.deb"; Archive = "debian"; Pool = "pool/main/g/gcc-14/libtsan2_14.2.0-19_amd64.deb"; Size = 2460216; Sha256 = "529d7f68227d16975076c5f842e8b687faea1b5df8e0dcf62e436d5402844ca5" },
    @{ Name = "libubsan1"; File = "libubsan1_14.2.0-19_amd64.deb"; Archive = "debian"; Pool = "pool/main/g/gcc-14/libubsan1_14.2.0-19_amd64.deb"; Size = 1074340; Sha256 = "9205a1bef7d6a52ffc06548e0cde169ff303e688c12d9be3a98f734449077e22" },
    @{ Name = "libhwasan0"; File = "libhwasan0_14.2.0-19_amd64.deb"; Archive = "debian"; Pool = "pool/main/g/gcc-14/libhwasan0_14.2.0-19_amd64.deb"; Size = 1487768; Sha256 = "2cdaf797cad8ac30a964ab081370682dd065ae1b0305a0be9d8e0e14cd0657d7" },
    @{ Name = "libquadmath0"; File = "libquadmath0_14.2.0-19_amd64.deb"; Archive = "debian"; Pool = "pool/main/g/gcc-14/libquadmath0_14.2.0-19_amd64.deb"; Size = 145068; Sha256 = "f5b51cf0ece3ec3bb7494d0cdbff3ce715ae00cfb2b6ed787f7db91319d64a7b" },
    @{ Name = "libgcc-14-dev"; File = "libgcc-14-dev_14.2.0-19_amd64.deb"; Archive = "debian"; Pool = "pool/main/g/gcc-14/libgcc-14-dev_14.2.0-19_amd64.deb"; Size = 2672328; Sha256 = "ca6f2d36d96b19b3eb71405b0b80134d8c89380b02204a2512e5c58ceb090628" },
    @{ Name = "gcc-14-x86-64-linux-gnu"; File = "gcc-14-x86-64-linux-gnu_14.2.0-19_amd64.deb"; Archive = "debian"; Pool = "pool/main/g/gcc-14/gcc-14-x86-64-linux-gnu_14.2.0-19_amd64.deb"; Size = 21389968; Sha256 = "a17ef039f1ba482051c3efb5c2c24070002e60dd0bd09fd456ec31481a11b725" },
    @{ Name = "gcc-14"; File = "gcc-14_14.2.0-19_amd64.deb"; Archive = "debian"; Pool = "pool/main/g/gcc-14/gcc-14_14.2.0-19_amd64.deb"; Size = 540064; Sha256 = "21500408b5019d8d29f70ce58488e2eea469a1adb4b5fd7db45e819b5efcac4e" },
    @{ Name = "libefivar1t64"; File = "libefivar1t64_38-3.1+b1_amd64.deb"; Archive = "debian"; Pool = "pool/main/e/efivar/libefivar1t64_38-3.1%2bb1_amd64.deb"; Size = 58460; Sha256 = "34bfb96ca9422af293aeac800438682112b4019adc5ed25728bc35dff4ad4ca4" },
    @{ Name = "libnvidia-rtcore"; File = "libnvidia-rtcore_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/libnvidia-rtcore_550.163.01-2_amd64.deb"; Size = 13272104; Sha256 = "78e6197dbf5cbf13813076369e9589f81591d28bbe2638526a131b6db5e3b7c0" },
    @{ Name = "pahole"; File = "pahole_1.30-1_amd64.deb"; Archive = "debian"; Pool = "pool/main/d/dwarves/pahole_1.30-1_amd64.deb"; Size = 258892; Sha256 = "08b8b559ab1707dc146880d329f1e96f011788a18d6d3dc7159accd488ae2712" },
    @{ Name = "mokutil"; File = "mokutil_0.7.2-1_amd64.deb"; Archive = "debian"; Pool = "pool/main/m/mokutil/mokutil_0.7.2-1_amd64.deb"; Size = 26744; Sha256 = "1918fd2775b06e35429a06c59586d548bcccd6c544684799a22ae532a8bb83e4" },
    @{ Name = "nvidia-vulkan-common"; File = "nvidia-vulkan-common_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/nvidia-vulkan-common_550.163.01-2_amd64.deb"; Size = 161876; Sha256 = "68131339e5df5553e14b29f6d25947cb448b2d9ce390297b705b557920efa787" },
    @{ Name = "nvidia-vulkan-icd"; File = "nvidia-vulkan-icd_550.163.01-2_amd64.deb"; Archive = "debian"; Pool = "pool/non-free/n/nvidia-graphics-drivers/nvidia-vulkan-icd_550.163.01-2_amd64.deb"; Size = 161336; Sha256 = "5da88f6434706800a0c0b6c5c8d723af6e3251c8f9bc522da548dbb9b6389267" }
)
$BauNvidiaMirrors = @{
    "debian" = @("https://deb.debian.org/debian/", "https://snapshot.debian.org/archive/debian/20261027T120000Z/");
    "debian-security" = @("https://deb.debian.org/debian-security/", "https://snapshot.debian.org/archive/debian-security/20261027T120000Z/")
}
# The latest BAU, so a laptop installed from an older stick gets `bau pack` too.
$BauZip = "https://github.com/BSAJabo258/linux-ai-biz/archive/refs/heads/main.zip"
$BauGpuSetup = "https://raw.githubusercontent.com/BSAJabo258/linux-ai-biz/main/image/live-build/config/includes.chroot/usr/local/sbin/bau-gpu-setup"

function Get-BauSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLower()
}

function Select-BauStick {
    # Bigger USB sticks and USB SSDs often call themselves "Fixed": also take any drive
    # on a USB disk. Never the Windows drive (that is not on USB).
    $usb = @(Get-Disk -ErrorAction SilentlyContinue | Where-Object { $_.BusType -eq "USB" } |
        Get-Partition -ErrorAction SilentlyContinue | Where-Object { $_.DriveLetter } |
        ForEach-Object { "$($_.DriveLetter):\" })
    $drives = @([IO.DriveInfo]::GetDrives() | Where-Object {
        $_.IsReady -and ($_.DriveType -eq "Removable" -or $usb -contains $_.Name) })
    if (-not $drives.Count) {
        Write-Host "No USB stick found. Plug one in (32 GB or more, exFAT) and run this again." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "USB sticks on this computer:"
    foreach ($d in $drives) {
        $gb = [math]::Round($d.TotalSize / 1GB, 1)
        $free = [math]::Round($d.AvailableFreeSpace / 1GB, 1)
        Write-Host ("  {0}  {1}  {2} GB, {3} GB free" -f $d.Name.Substring(0, 2), $d.VolumeLabel, $gb, $free)
    }
    $letter = (Read-Host "Type the letter of the stick to fill (for example E)").Trim().TrimEnd(":", "\").ToUpper()
    foreach ($d in $drives) {
        if ($d.Name.Substring(0, 1).ToUpper() -eq $letter -and $letter.Length -eq 1) {
            # FAT32 cannot hold a file over 4 GB, and the desktop's model is 5.7 GB.
            if ($d.DriveFormat -eq "FAT32") {
                Write-Host "$letter is formatted FAT32, which cannot hold the 5.7 GB model. Format it exFAT first (docs/PACK.md). Nothing written." -ForegroundColor Yellow
                exit 1
            }
            return $d.Name
        }
    }
    Write-Host "$letter is not one of the USB sticks above. Nothing written." -ForegroundColor Yellow
    exit 1
}

function Get-BauCurl {
    # The real curl program, never PowerShell's "curl" alias for Invoke-WebRequest.
    $c = Get-Command curl.exe -CommandType Application -ErrorAction SilentlyContinue
    if (-not $c) { $c = Get-Command curl -CommandType Application -ErrorAction SilentlyContinue }
    if (-not $c) {
        Write-Host "curl.exe was not found (Windows 10 and 11 include it)." -ForegroundColor Yellow
        exit 1
    }
    return @($c)[0].Source
}

function Get-BauFile([string]$Curl, [string[]]$Urls, [string]$Final, [string]$Sha256, [string]$Label) {
    # Returns $true when $Final is in place and matches its pinned SHA-256.
    if (Test-Path -LiteralPath $Final) {
        if ((Get-BauSha256 $Final) -eq $Sha256) { Write-Host "${Label}: already on the stick, checked."; return $true }
        Remove-Item -LiteralPath $Final
    }
    $part = "$Final.part"
    foreach ($url in $Urls) {
        Write-Host "${Label}: downloading..."
        & $Curl -L --fail --retry 3 -C - -o $part $url
        if ($LASTEXITCODE -ne 0) { continue }
        if ((Get-BauSha256 $part) -ne $Sha256) {
            Remove-Item -LiteralPath $part
            Write-Host "${Label}: the file does not match its pinned SHA-256, so it was deleted." -ForegroundColor Red
            return $false
        }
        Move-Item -LiteralPath $part -Destination $Final -Force
        Write-Host "${Label}: downloaded and checked." -ForegroundColor Green
        return $true
    }
    Write-Host "${Label}: download stopped. Run this again to carry on." -ForegroundColor Yellow
    return $false
}

function Write-BauReadme([string]$Pack) {
    $text = @"
BAU PACK
========
This folder holds the BAU laptop's local AI models (models\) and, if you made one,
your locked keys file (BAU-KEYS.enc). Every model was checked against its pinned
SHA-256 when it was downloaded, and is checked again on the laptop.

On the BAU laptop, plug in this stick and open it once in the file manager.

If the laptop has no Wi-Fi (laptops installed from a stick made before 18 October
2026), first open a terminal and type these four lines:
  cd /media/`$USER/*/BAU-PACK/wifi
  sha256sum -c SHA256SUMS
  sudo apt install ./*.deb
  sudo systemctl restart NetworkManager
Then pick your Wi-Fi from the network icon. Once it is connected, bring BAU up to date:
  sudo /opt/bau/venv/bin/pip install --no-deps --upgrade /media/`$USER/*/BAU-PACK/bau-main.zip

Then, in the terminal:
  sudo bau pack install
Answer yes or no to each question. Nothing changes without your yes. At the end it
writes laptop-report.txt onto this stick (the laptop's network card and firmware,
with addresses and Wi-Fi names hidden).

Nothing on this stick runs by itself when you plug it in.
"@
    [IO.File]::WriteAllText((Join-Path $Pack "README.txt"), $text.Replace("`r`n", "`n"))
}

if ($MyInvocation.InvocationName -ne ".") {
    $models = $BauModels
    $debs = @()
    foreach ($d in $BauDebs) {
        $urls = @(); foreach ($mirror in $BauDebMirrors) { $urls += ($mirror + $d.Pool) }
        $debs += @{ Name = $d.Name; File = $d.File; Size = $d.Size; Sha256 = $d.Sha256; Urls = $urls }
    }
    $nvidia = @()
    foreach ($d in $BauNvidiaDebs) {
        $urls = @(); foreach ($mirror in $BauNvidiaMirrors[$d.Archive]) { $urls += ($mirror + $d.Pool) }
        $nvidia += @{ Name = $d.Name; File = $d.File; Size = $d.Size; Sha256 = $d.Sha256; Urls = $urls }
    }
    $zip = $BauZip
    if ($Manifest) {
        # Tests: the same lists with local links.
        $j = ConvertFrom-Json (Get-Content -Raw -LiteralPath $Manifest)
        $models = @(); foreach ($m in $j.Models) { $models += $m }
        $debs = @(); foreach ($d in $j.Debs) { $debs += $d }
        $nvidia = @(); foreach ($d in $j.Nvidia) { $nvidia += $d }
        $zip = $j.BauZip
        $BauGpuSetup = $j.GpuSetup
    }
    if (-not $Target) { $Target = Select-BauStick }
    $pack = Join-Path $Target "BAU-PACK"
    $dir = Join-Path $pack "models"

    try {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $probe = Join-Path $pack ".bau-write-test"
        [IO.File]::WriteAllText($probe, "ok")
        Remove-Item -LiteralPath $probe
    } catch {
        Write-Host "Cannot write to $Target. If it still holds a BAU installer image, format it" -ForegroundColor Yellow
        Write-Host "first in File Explorer (right-click the drive, Format, exFAT) - that erases it."
        exit 1
    }

    $need = [long]50MB
    foreach ($m in $models) {
        $f = Join-Path $dir $m.File
        if (-not (Test-Path -LiteralPath $f)) { $need += [long]$m.Size }
    }
    foreach ($d in $nvidia) { $need += [long]$d.Size }
    try {
        $free = (New-Object IO.DriveInfo ([IO.Path]::GetPathRoot((Resolve-Path $Target).Path))).AvailableFreeSpace
        if ($free -lt $need) {
            Write-Host ("Not enough space: {0:N1} GB needed, {1:N1} GB free." -f ($need / 1GB), ($free / 1GB)) -ForegroundColor Yellow
            exit 1
        }
    } catch { }

    Write-Host "This fills $pack with:"
    foreach ($m in $models) { Write-Host ("  {0}  ({1:N1} GB) {2}" -f $m.Id, ($m.Size / 1GB), $m.Role) }
    Write-Host "  the desktop's NVIDIA driver, to install without the internet (0.2 GB)"
    if (-not $Yes) {
        $ok = Read-Host "Go ahead? [y/N]"
        if ($ok -notmatch '^[yY]') { Write-Host "Nothing downloaded."; exit 0 }
    }

    $curl = Get-BauCurl
    $failed = 0
    foreach ($m in $models) {
        if (-not (Get-BauFile $curl @($m.Url) (Join-Path $dir $m.File) $m.Sha256 $m.Id)) { $failed++ }
    }

    $wifi = Join-Path $pack "wifi"
    New-Item -ItemType Directory -Force -Path $wifi | Out-Null
    $sums = @()
    foreach ($d in $debs) {
        if (Get-BauFile $curl @($d.Urls) (Join-Path $wifi $d.File) $d.Sha256 $d.Name) {
            $sums += "$($d.Sha256)  $($d.File)"
        } else { $failed++ }
    }
    [IO.File]::WriteAllText((Join-Path $wifi "SHA256SUMS"), (($sums -join "`n") + "`n"))

    # The NVIDIA driver files and the newest bau-gpu-setup, so the desktop needs no internet.
    $nv = Join-Path $pack "nvidia"
    New-Item -ItemType Directory -Force -Path $nv | Out-Null
    $sums = @()
    foreach ($d in $nvidia) {
        if (Get-BauFile $curl @($d.Urls) (Join-Path $nv $d.File) $d.Sha256 $d.Name) {
            $sums += "$($d.Sha256)  $($d.File)"
        } else { $failed++ }
    }
    [IO.File]::WriteAllText((Join-Path $nv "SHA256SUMS"), (($sums -join "`n") + "`n"))
    [IO.File]::WriteAllText((Join-Path $nv "KERNEL"), "$BauNvidiaKernel`n")
    $setup = Join-Path $nv "bau-gpu-setup"
    & $curl -L --fail --retry 3 -s -o "$setup.part" $BauGpuSetup
    if ($LASTEXITCODE -eq 0) { Move-Item -LiteralPath "$setup.part" -Destination $setup -Force }
    else { Write-Host "bau-gpu-setup: download stopped. Run this again." -ForegroundColor Yellow; $failed++ }

    # Not pinned (it changes with every update): it comes from your own GitHub repository.
    $zipFile = Join-Path $pack "bau-main.zip"
    Write-Host "BAU (latest): downloading..."
    & $curl -L --fail --retry 3 -o "$zipFile.part" $zip
    if ($LASTEXITCODE -eq 0) {
        Move-Item -LiteralPath "$zipFile.part" -Destination $zipFile -Force
    } else {
        if (Test-Path -LiteralPath "$zipFile.part") { Remove-Item -LiteralPath "$zipFile.part" }
        Write-Host "BAU (latest): download stopped. Run this again." -ForegroundColor Yellow
        $failed++
    }

    $keys = Join-Path $PSScriptRoot "BAU-KEYS.enc"
    if (Test-Path -LiteralPath $keys) {
        Copy-Item -LiteralPath $keys -Destination (Join-Path $pack "BAU-KEYS.enc") -Force
        Write-Host "BAU-KEYS.enc: copied (it stays locked with your passphrase)."
    }
    Write-BauReadme $pack

    Write-Host ""
    if ($failed) {
        Write-Host "$failed file(s) are not on the stick yet. Run this again." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "The BAU Pack is ready." -ForegroundColor Green
    Write-Host "On the laptop: plug it in, open it once in the file manager, then: sudo bau pack install"
    exit 0
}
