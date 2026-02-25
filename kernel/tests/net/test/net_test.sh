#!/bin/bash
if [[ -n "${verbose}" ]]; then
  echo 'Current working directory:'
  echo " - according to builtin:  [$(pwd)]"
  echo " - according to /bin/pwd: [$(/bin/pwd)]"
  echo

  echo 'Shell environment:'
  env
  echo

  echo -n "net_test.sh (pid $$, parent ${PPID}, tty $(tty)) running [$0] with args:"
  for arg in "$@"; do
    echo -n " [${arg}]"
  done
  echo
  echo
fi

if [[ "$(tty)" == '/dev/console' ]]; then
  ARCH="$(uname -m)"
  # Underscore is illegal in hostname, replace with hyphen
  ARCH="${ARCH//_/-}"

  # setsid + /dev/tty{,AMA,S}0 allows bash's job control to work, ie. Ctrl+C/Z
  if [[ -c '/dev/tty0' ]]; then
    # exists in UML, does not exist on graphics/vga/curses-less QEMU
    CON='/dev/tty0'
    hostname "uml-${ARCH}"
  elif [[ -c '/dev/ttyAMA0' ]]; then
    # Qemu for arm (note: /dev/ttyS0 also exists for exitcode)
    CON='/dev/ttyAMA0'
    hostname "qemu-${ARCH}"
  elif [[ -c '/dev/ttyS0' ]]; then
    # Qemu for x86 (note: /dev/ttyS1 also exists for exitcode)
    CON='/dev/ttyS0'
    hostname "qemu-${ARCH}"
  else
    # Can't figure it out, job control won't work, tough luck
    echo 'Unable to figure out proper console - job control will not work.' >&2
    CON=''
    hostname "local-${ARCH}"
  fi

  unset ARCH

  echo -n "$(hostname): Currently tty[/dev/console], but it should be [${CON}]..."

  if [[ -n "${CON}" ]]; then
    # Redirect std{in,out,err} to the console equivalent tty
    # which actually supports all standard tty ioctls
    exec <"${CON}" >&"${CON}"

    # Bash wants to be session leader, hence need for setsid
    echo " re-executing..."
    exec /usr/bin/setsid "$0" "$@"
    # If the above exec fails, we just fall through...
    # (this implies failure to *find* setsid, not error return from bash,
    #  in practice due to image construction this cannot happen)
  else
    echo
  fi

  # In case we fall through, clean up
  unset CON
fi

if [[ -n "${verbose}" ]]; then
  echo 'TTY settings:'
  stty
  echo

  echo 'TTY settings (verbose):'
  stty -a
  echo

  echo 'Restoring TTY sanity...'
fi

stty sane
stty 115200
[[ -z "${console_cols}" ]] || stty columns "${console_cols}"
[[ -z "${console_rows}" ]] || stty rows    "${console_rows}"

if [[ -n "${verbose}" ]]; then
  echo

  echo 'TTY settings:'
  stty
  echo

  echo 'TTY settings (verbose):'
  stty -a
  echo
fi

# By the time we get here we should have a sane console:
#  - 115200 baud rate
#  - appropriate (and known) width and height (note: this assumes
#    that the terminal doesn't get further resized)
#  - it is no longer /dev/console, so job control should function
#    (this means working ctrl+c [abort] and ctrl+z [suspend])


# This defaults to 60 which is needlessly long during boot
# (we will reset it back to the default later)
echo 0 > /proc/sys/kernel/random/urandom_min_reseed_secs

if [[ -n "${entropy}" ]]; then
  echo "adding entropy from hex string [${entropy}]" >&2

  # In kernel/include/uapi/linux/random.h RNDADDENTROPY is defined as
  # _IOW('R', 0x03, int[2]) =(R is 0x52)= 0x40085203 = 1074287107
  /usr/bin/python 3>/dev/random <<EOF
import fcntl, struct
rnd = '${entropy}'.decode('base64')
fcntl.ioctl(3, 0x40085203, struct.pack('ii', len(rnd) * 8, len(rnd)) + rnd)
EOF

fi

# Make sure the urandom pool has a chance to initialize before we reset
# the reseed timer back to 60 seconds.  One timer tick should be enough.
sleep 1.1

# By this point either 'random: crng init done' (newer kernels)
# or 'random: nonblocking pool is initialized' (older kernels)
# should have been printed out to dmesg/console.

# Reset it back to boot time default
echo 60 > /proc/sys/kernel/random/urandom_min_reseed_secs


# In case IPv6 is compiled as a module.
[ -f /proc/net/if_inet6 ] || insmod $DIR/kernel/net-next/net/ipv6/ipv6.ko

# Minimal network setup.
ip link set lo up
ip link set lo mtu 16436
ip link set eth0 up

# Allow people to run ping.
echo "0 65536" > /proc/sys/net/ipv4/ping_group_range

# Read environment variables passed to the kernel to determine if script is
# running on builder and to find which test to run.

if [ "$net_test_mode" != "builder" ]; then
  # Fall out to a shell once the test completes or if there's an error.
  trap "exec /bin/bash" ERR EXIT
fi

echo -e "Running $net_test $net_test_args\n"
$net_test $net_test_args

# Write exit code of net_test to a file so that the builder can use it
# to signal failure if any tests fail.
echo $? >$net_test_exitcode
