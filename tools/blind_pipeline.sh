#!/bin/zsh
# The whole analysis of one recording, run in one go so that no step is tuned by hand:
#   1. put back samples a busy server lost (fix_drops)          -> data/iq/<name>r/
#   2. search with the receiver at its listed position, then fit receiver and transmitter (site_run rxfit=2)
#   3. wrong-track nulls (spectrum flip plus time shifts)        -> results/<name>r_null.jsonl
#   4. rules v1 / v2 / v2.2 as defined in jf/rules.py            -> results/<name>r_rules.json
# usage: blind_pipeline.sh name iq_prefix adsb rx_lat rx_lon freq_hz rx_h tx_h ground_h "shift1,shift2,..." [car_lo car_hi]
set -u
name=$1; prefix=$2; adsb=$3; rx_lat=$4; rx_lon=$5; freq=$6; rx_h=$7; tx_h=$8; ground_h=$9; shifts=${10}
car_lo=${11:-500}; car_hi=${12:-3000}
# any further key=value words (e.g. rx_e=... rx_n=... in metres for a receiver whose listed position carries a known
# offset, or max_gap=30 for 20-s position feeds) are forwarded unchanged to steps 2-4
extra=()
if [ $# -gt 12 ]; then shift 12; extra=("$@"); fi
P=${0:A:h:h}
cd $P || exit 1
PY=$P/.venv/bin/python
rname=${name}r
rprefix=data/iq/$rname/$(basename $prefix)
echo "== 1. repair ($name -> $rname)"
$PY tools/fix_drops.py $prefix $rprefix car_lo=$car_lo car_hi=$car_hi | tee results/${rname}_fix_drops.txt
echo "== 2. search + joint fit"
$PY analysis/site_run.py $rname $rprefix $adsb $rx_lat $rx_lon $freq rx_h=$rx_h tx_h=$tx_h ground_h=$ground_h car_lo=$car_lo car_hi=$car_hi rxfit=2 out=results/${rname}_fix_rxfit.json "${extra[@]}" | tee results/${rname}_site_run.txt
echo "== 3. wrong-track nulls"
$PY analysis/null_try.py $rname $rprefix $adsb $rx_lat $rx_lon $freq rx_h=$rx_h tx_h=$tx_h ground_h=$ground_h shifts=$shifts flip=1 out=results/${rname}_null.jsonl "${extra[@]}" | tee results/${rname}_null.txt
echo "== 4. rules"
$PY analysis/rule_v2.py $rname $adsb $rx_lat $rx_lon $freq rx_h=$rx_h tx_h=$tx_h ground_h=$ground_h "${extra[@]}" | tee results/${rname}_rules.txt
echo "== done: results/${rname}_rules.json holds the early rules; run analysis/rule_v31.py for the final rule before you open a sealed reference"
