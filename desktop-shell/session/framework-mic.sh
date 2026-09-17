#!/usr/bin/env bash
# Framework 13 AMD Ryzen AI 300: pick the UCM profile that exposes the real
# ALC285 internal mic (Mic2) instead of the phantom ACP Digital Microphone
# (Mic1) plus an empty headset jack. Safe no-op on other machines.
#
# Keep gain low: UCM Internal Mic Boost clips hard above ~45%.

set -euo pipefail

card=""
headphones_available=no
mic2_profile_available=no

while IFS= read -r line; do
    case "$line" in
        "Card #"*) card="" ;;
        *$'\tName: alsa_card.'*) card=${line##*$'\tName: '} ;;
    esac
    [[ -n "$card" ]] || continue
    if [[ "$line" == *$'\tHiFi (Headphones, Mic1, Mic2):'*available:\ yes* ]]; then
        headphones_available=yes
        mic2_card=$card
    fi
    if [[ "$line" == *$'\tHiFi (Mic1, Mic2, Speaker):'*available:\ yes* ]]; then
        mic2_profile_available=yes
        mic2_card=$card
    fi
done < <(pactl list cards 2>/dev/null)

[[ "${mic2_profile_available}" == yes ]] || exit 0

if [[ "$headphones_available" == yes ]]; then
    profile="HiFi (Headphones, Mic1, Mic2)"
else
    profile="HiFi (Mic1, Mic2, Speaker)"
fi

pactl set-card-profile "$mic2_card" "$profile"

src=""
for _ in 1 2 3 4 5 6 7 8 9 10; do
    src=$(pactl list short sources 2>/dev/null | awk '/HiFi__Mic2__source/ { print $2; exit }')
    [[ -n "$src" ]] && break
    sleep 0.15
done
[[ -n "$src" ]] || exit 0

pactl set-default-source "$src"
pactl set-source-volume "$src" 30%
