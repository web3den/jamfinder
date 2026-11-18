#!/bin/zsh
# Wait for an IQ recording to finish, then run the analysis once, untouched, and the rules v3 to v3.2.
# The recording is finished when its sidecar <prefix>.json says "partial": false (spy_record writes that on exit);
# a recording that has not started yet is waited for (up to 3 h), so this can be armed before the recorder.
# usage: run_after.sh <name> <iq prefix> <rx_lat> <rx_lon> <freq_hz> <rx_h> <tx_h> <ground_h> "<shifts>" [key=value ...]
#   positions: every <dir of prefix>/adsb_*.jsonl.gz, merged in time order
#   key=value words (rx_e=... rx_n=..., max_gap=30, ...) are forwarded to the pipeline steps and the rule
set -u
name=$1; prefix=$2; rx_lat=$3; rx_lon=$4; freq=$5; rx_h=$6; tx_h=$7; ground_h=$8; shifts=$9
shift 9
extra=("$@")
P=${0:A:h:h}
cd $P || exit 1
PY=$P/.venv/bin/python
d=$(dirname $prefix)
finished() { $PY -c "import json,sys; m=json.load(open('$prefix.json')); sys.exit(0 if m.get('partial') is False else 1)" 2>/dev/null; }
echo "== $name: waiting for $prefix.json to say finished ($(date -u +%H:%M:%S) UTC)"
n=0
until finished || [ $n -ge 720 ]; do sleep 15; n=$((n+1)); done
if ! finished; then echo "== $name: recording never finished within 3 h; giving up"; exit 2; fi
if $PY -c "import json,sys; sys.exit(0 if json.load(open('$prefix.json')).get('aborted') else 1)" 2>/dev/null; then
  echo "== $name: the recorder aborted ($($PY -c "import json; print(json.load(open('$prefix.json')).get('aborted'))")); no pipeline run"; exit 3
fi
sleep 30   # let the position recorders run past the end of the IQ
echo "== $name: recording finished ($(date -u +%H:%M:%S) UTC)"
# at most two pipelines at a time: the repaired float32 copy is about four times the raw recording, and concurrent
# runs each hold one. Two copies (about 2 GB) fitted on the small disk this was written on, three might not
lock=""
w=0
while [ -z "$lock" ]; do
  for cand in results/.pipeline_lock1 results/.pipeline_lock2; do
    if mkdir $cand 2>/dev/null; then lock=$cand; break; fi
  done
  [ -z "$lock" ] && { sleep 20; w=$((w+20)); }
done
trap 'rmdir $lock 2>/dev/null' EXIT
echo "== $name: pipeline slot $lock taken after ${w}s ($(date -u +%H:%M:%S) UTC)"
files=($d/adsb_*.jsonl.gz)
$PY tools/merge_adsb.py $d/adsb_all.jsonl.gz $files | tee results/${name}_merge.txt
zsh tools/blind_pipeline.sh $name $prefix $d/adsb_all.jsonl.gz $rx_lat $rx_lon $freq $rx_h $tx_h $ground_h "$shifts" 500 3000 "${extra[@]}"
# wrong-time-tracks null (rule v3.2's standard set, when tracks of the same site from another hour or day exist):
# a symlink or file <dir>/wrongtime_tracks.jsonl.gz names them; its row joins the pipeline's nulls for the rule
nulls_all=results/${name}r_null.jsonl
if [ -e $d/wrongtime_tracks.jsonl.gz ]; then
  $PY analysis/null_wrongtime.py ${name}r data/iq/${name}r/$(basename $prefix) $d/adsb_all.jsonl.gz $d/wrongtime_tracks.jsonl.gz $rx_lat $rx_lon $freq \
      rx_h=$rx_h tx_h=$tx_h ground_h=$ground_h "${extra[@]}" out=results/${name}r_null_wrongtime.jsonl | tee results/${name}r_null_wrongtime.txt
  cat results/${name}r_null.jsonl results/${name}r_null_wrongtime.jsonl > results/${name}r_null_all.jsonl
  nulls_all=results/${name}r_null_all.jsonl
fi
$PY analysis/rule_v31.py ${name}r $d/adsb_all.jsonl.gz $rx_lat $rx_lon ground_h=$ground_h nulls=$nulls_all "${extra[@]}" | tee results/${name}r_rules_v31.txt
# the repaired copy is float32 (about four times the raw recording) and every later analysis uses the baseband cache
# results/<name>r_bb.npz; once that cache exists the copy is removed (regenerable with tools/fix_drops.py), because
# these copies once filled the disk
if [ -s results/${name}r_bb.npz ]; then rm -f data/iq/${name}r/*.iq && echo "== $name: repaired IQ copy removed (baseband cache kept)"; fi
echo "== $name: done ($(date -u +%H:%M:%S) UTC): results/${name}r_rules.json, results/${name}r_rules_v31.json"
