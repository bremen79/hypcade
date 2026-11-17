# ROM policy results

Readable summary of the canonical
[one-life results](verification/one-life-ranges.json) ([CSV](verification/one-life-ranges.csv)).
All eleven supported ROM profiles and all 102 setting/objective combinations
are represented. Update the canonical dataset first when results change.

## Packaged guidance

Both objectives are calculated before deciding which policies to package.
The APK retains Max score alone when ROM-derived comparisons certify that it
requires at most one extra accepted input for corresponding room allocations.
This applies to eight of the eleven calculated ROM profiles; three retain
separate strategies.

<table border="1" rules="all" cellspacing="0" cellpadding="6" style="border-collapse: collapse;">
<thead>
<tr><th scope="col">ROM profiles</th><th scope="col">Packaged policies</th><th scope="col">Show moves choices</th></tr>
</thead>
<tbody>
<tr><td>US Dragon's Lair A–F (<code>lair_a</code>–<code>lair_f</code>)</td><td>Max score</td><td>Off / On</td></tr>
<tr><td>European and Italian Dragon's Lair (<code>laireuro</code>, <code>lair_ita</code>)</td><td>Max score</td><td>Off / On</td></tr>
<tr><td>DLE21, Space Ace A3 and SAE 1.0 (<code>dle21</code>, <code>ace</code>, <code>sae</code>)</td><td>Max score and Fewest moves</td><td>Off / Max score / Fewest moves</td></tr>
</tbody>
</table>

On uses Max score. Watch Mode follows the selected policy; with Show moves Off,
it uses Max score while hiding guidance. Timings come from the running ROM,
including its current skill and difficulty, rather than packaged timing tables.

The one-input comparison concerns corresponding room allocations, not unrelated
randomized plays. European/Italian room input costs coincide; the US ROM room
histories limit the extra cost to one input. See
[the retention contract](../../tools/offline-moves/COST-FUTURE.md#policy-retention)
and [the per-ROM audit](verification/policy-retention.json).

The results below still describe both complete calculated policies. Their
rankings and proof certificates remain in the source bundle even when Fewest
moves is omitted from the APK. A displayed Fewest result therefore does not
imply that it is offered separately in the app. UI details are in
[Show moves](../README.md#video-sound-and-moves); testing and size measurements
are in [the validation guide](../VALIDATION.md).

## Reading the tables

Results use **minimum - maximum** for the indicated policy and metric.
When both endpoints are known and equal, only one number is shown. Inputs are accepted cardinal-direction/button commands, excluding
coins, Start and ignored input pulses.
An unparenthesized endpoint is an established attainable extremum. A number
in parentheses, such as `(192)`, is only a ROM-derived bound whose attainment
has not been established. A `?` is reserved for an endpoint without a known
bound. A single successful run does not establish an entire range.

The objective values are bold: the attained minimum input count for **Fewest
inputs**, and the attained maximum score for **Max score**. Other endpoints
are unbolded, including all parenthesized bounds. Each policy has separate
input-count and score columns; extrema
in different columns need not occur on the same play. Operator levels are the
internal indices in the result data and are grouped when all displayed values
agree.

The objectives concern one-life play without deliberate deaths, probabilities
or expectations. Optimality means a non-zero possibility of attaining the
objective. Full proof scope and runtime evidence are maintained in
[VALIDATION.md](../VALIDATION.md).

## Dragon's Lair Enhanced 2.1

DLE21 uses its authored fixed setting; it has no operator-difficulty option.

<table border="1" rules="all" cellspacing="0" cellpadding="6" style="border-collapse: collapse;">
<thead>
<tr>
<th scope="col">ROM</th>
<th scope="col">Skill / operator level</th>
<th scope="col">Fewest inputs: inputs min - max</th>
<th scope="col">Fewest inputs: score min - max</th>
<th scope="col">Max score: score min - max</th>
<th scope="col">Max score: inputs min - max</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>dle21</code></td>
<td>Fixed</td>
<td align="right"><strong>147</strong></td>
<td align="right">314,457</td>
<td align="right"><strong>333,333</strong></td>
<td align="right">155</td>
</tr>
</tbody>
</table>

## US Dragon's Lair revisions A–F

Each revision covers operator levels 0–3. The bold objective values have
attaining executions. Unestablished extrema show the available bounds in
parentheses. Neither objective is guaranteed on every randomized start.
The additional E/F extrema are certified in the
[attained-endpoint report](verification/late-attained-ranges.json) and
[direct ROM acceptance-count report](verification/counted-attained-ranges.json).

<table border="1" rules="all" cellspacing="0" cellpadding="6" style="border-collapse: collapse;">
<thead>
<tr>
<th scope="col">ROM</th>
<th scope="col">Skill / operator level</th>
<th scope="col">Fewest inputs: inputs min - max</th>
<th scope="col">Fewest inputs: score min - max</th>
<th scope="col">Max score: score min - max</th>
<th scope="col">Max score: inputs min - max</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>lair_a</code></td>
<td>0–1</td>
<td align="right"><strong>173</strong> - (218)</td>
<td align="right">(254,217) - (376,516)</td>
<td align="right">(254,712) - <strong>377,011</strong></td>
<td align="right">(173) - (219)</td>
</tr>
<tr>
<td><code>lair_a</code></td>
<td>2</td>
<td align="right"><strong>185</strong> - (208)</td>
<td align="right">(273,748) - (364,661)</td>
<td align="right">(274,243) - <strong>365,156</strong></td>
<td align="right">(186) - (209)</td>
</tr>
<tr>
<td><code>lair_a</code></td>
<td>3</td>
<td align="right"><strong>179</strong> - (208)</td>
<td align="right">(273,369) - (364,661)</td>
<td align="right">(273,864) - <strong>365,156</strong></td>
<td align="right">(180) - (209)</td>
</tr>
<tr>
<td><code>lair_b</code></td>
<td>0–1</td>
<td align="right"><strong>173</strong> - (218)</td>
<td align="right">(254,217) - (376,516)</td>
<td align="right">(254,712) - <strong>377,011</strong></td>
<td align="right">(173) - (219)</td>
</tr>
<tr>
<td><code>lair_b</code></td>
<td>2</td>
<td align="right"><strong>179</strong> - (211)</td>
<td align="right">(268,782) - (365,156)</td>
<td align="right">(268,782) - <strong>365,651</strong></td>
<td align="right">(180) - (212)</td>
</tr>
<tr>
<td><code>lair_b</code></td>
<td>3</td>
<td align="right"><strong>177</strong> - (208)</td>
<td align="right">(268,403) - (364,661)</td>
<td align="right">(268,403) - <strong>365,156</strong></td>
<td align="right">(177) - (209)</td>
</tr>
<tr>
<td><code>lair_c</code></td>
<td>0–1</td>
<td align="right"><strong>173</strong> - (218)</td>
<td align="right">(254,217) - (376,516)</td>
<td align="right">(254,712) - <strong>377,011</strong></td>
<td align="right">(173) - (219)</td>
</tr>
<tr>
<td><code>lair_c</code></td>
<td>2</td>
<td align="right"><strong>179</strong> - (211)</td>
<td align="right">(268,782) - (365,156)</td>
<td align="right">(268,782) - <strong>365,651</strong></td>
<td align="right">(180) - (212)</td>
</tr>
<tr>
<td><code>lair_c</code></td>
<td>3</td>
<td align="right"><strong>177</strong> - (208)</td>
<td align="right">(268,403) - (364,661)</td>
<td align="right">(268,403) - <strong>365,156</strong></td>
<td align="right">(177) - (209)</td>
</tr>
<tr>
<td><code>lair_d</code></td>
<td>0–1</td>
<td align="right"><strong>173</strong> - (218)</td>
<td align="right">(254,217) - (376,516)</td>
<td align="right">(254,712) - <strong>377,011</strong></td>
<td align="right">(173) - (219)</td>
</tr>
<tr>
<td><code>lair_d</code></td>
<td>2</td>
<td align="right"><strong>179</strong> - (211)</td>
<td align="right">(268,782) - (365,156)</td>
<td align="right">(268,782) - <strong>365,651</strong></td>
<td align="right">(180) - (212)</td>
</tr>
<tr>
<td><code>lair_d</code></td>
<td>3</td>
<td align="right"><strong>177</strong> - (208)</td>
<td align="right">(268,403) - (364,661)</td>
<td align="right">(268,403) - <strong>365,156</strong></td>
<td align="right">(177) - (209)</td>
</tr>
<tr>
<td><code>lair_e</code></td>
<td>0–1</td>
<td align="right"><strong>197</strong></td>
<td align="right">325,753</td>
<td align="right"><strong>326,248</strong></td>
<td align="right">198</td>
</tr>
<tr>
<td><code>lair_e</code></td>
<td>2</td>
<td align="right"><strong>197</strong> - 198</td>
<td align="right">325,753 - 326,124</td>
<td align="right">326,248 - <strong>326,619</strong></td>
<td align="right">198 - 199</td>
</tr>
<tr>
<td><code>lair_e</code></td>
<td>3</td>
<td align="right"><strong>191</strong> - 198</td>
<td align="right">325,374 - 326,124</td>
<td align="right">325,869 - <strong>326,619</strong></td>
<td align="right">(192) - 199</td>
</tr>
<tr>
<td><code>lair_f</code></td>
<td>0–1</td>
<td align="right"><strong>197</strong></td>
<td align="right">325,753</td>
<td align="right"><strong>326,248</strong></td>
<td align="right">198</td>
</tr>
<tr>
<td><code>lair_f</code></td>
<td>2</td>
<td align="right"><strong>197</strong> - 198</td>
<td align="right">325,753 - 326,124</td>
<td align="right">326,248 - <strong>326,619</strong></td>
<td align="right">198 - 199</td>
</tr>
<tr>
<td><code>lair_f</code></td>
<td>3</td>
<td align="right"><strong>191</strong> - 198</td>
<td align="right">325,374 - 326,124</td>
<td align="right">325,869 - <strong>326,619</strong></td>
<td align="right">(192) - 199</td>
</tr>
</tbody>
</table>

## Space Ace A3

All three skills and all four operator levels are covered. Values agree across
levels 0–3 for each skill; the running ROM still supplies skill/difficulty timers
and in-game difficulty progression.

<table border="1" rules="all" cellspacing="0" cellpadding="6" style="border-collapse: collapse;">
<thead>
<tr>
<th scope="col">ROM</th>
<th scope="col">Skill / operator level</th>
<th scope="col">Fewest inputs: inputs min - max</th>
<th scope="col">Fewest inputs: score min - max</th>
<th scope="col">Max score: score min - max</th>
<th scope="col">Max score: inputs min - max</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>ace</code></td>
<td>Cadet · 0–3</td>
<td align="right"><strong>85</strong></td>
<td align="right">185,686</td>
<td align="right"><strong>257,784</strong></td>
<td align="right">134</td>
</tr>
<tr>
<td><code>ace</code></td>
<td>Captain · 0–3</td>
<td align="right"><strong>109</strong></td>
<td align="right">213,098</td>
<td align="right"><strong>289,102</strong></td>
<td align="right">166</td>
</tr>
<tr>
<td><code>ace</code></td>
<td>Ace · 0–3</td>
<td align="right"><strong>136</strong></td>
<td align="right">213,092</td>
<td align="right"><strong>374,338</strong></td>
<td align="right">217</td>
</tr>
</tbody>
</table>

## Space Ace Enhancement 1.0

Both operator levels (0 = Easy, 1 = Hard) are covered at each skill. Cadet Max
score has a timing-dependent scene-selection range; its upper endpoint is the
attainable optimum under the chosen criterion.

<table border="1" rules="all" cellspacing="0" cellpadding="6" style="border-collapse: collapse;">
<thead>
<tr>
<th scope="col">ROM</th>
<th scope="col">Skill / operator level</th>
<th scope="col">Fewest inputs: inputs min - max</th>
<th scope="col">Fewest inputs: score min - max</th>
<th scope="col">Max score: score min - max</th>
<th scope="col">Max score: inputs min - max</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>sae</code></td>
<td>Cadet · 0–1</td>
<td align="right"><strong>85</strong></td>
<td align="right">150,396</td>
<td align="right">318,706 - <strong>319,498</strong></td>
<td align="right">151</td>
</tr>
<tr>
<td><code>sae</code></td>
<td>Captain · 0–1</td>
<td align="right"><strong>110</strong></td>
<td align="right">179,410</td>
<td align="right"><strong>366,836</strong></td>
<td align="right">183</td>
</tr>
<tr>
<td><code>sae</code></td>
<td>Ace · 0–1</td>
<td align="right"><strong>119</strong></td>
<td align="right">188,112</td>
<td align="right"><strong>398,412</strong></td>
<td align="right">212</td>
</tr>
</tbody>
</table>

## European and Italian Dragon's Lair

Both revisions cover levels 0–3. European room reordering preserves the totals.
The Italian row shows parenthesized room-pool bounds across generated queues;
its attainable overall extrema are unknown.

<table border="1" rules="all" cellspacing="0" cellpadding="6" style="border-collapse: collapse;">
<thead>
<tr>
<th scope="col">ROM</th>
<th scope="col">Skill / operator level</th>
<th scope="col">Fewest inputs: inputs min - max</th>
<th scope="col">Fewest inputs: score min - max</th>
<th scope="col">Max score: score min - max</th>
<th scope="col">Max score: inputs min - max</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>laireuro</code></td>
<td>0–3</td>
<td align="right"><strong>207</strong></td>
<td align="right">202,599</td>
<td align="right"><strong>202,599</strong></td>
<td align="right">207</td>
</tr>
<tr>
<td><code>lair_ita</code></td>
<td>0–3</td>
<td align="right">(53) - (91)</td>
<td align="right">(53,549) - (97,650)</td>
<td align="right">(53,549) - (97,650)</td>
<td align="right">(53) - (91)</td>
</tr>
</tbody>
</table>

The Italian bounds allow pool choices independently; joint RNG attainment of
their endpoints is not established. The recorded queue's 76 inputs and 88,250
points do not establish overall extrema, so they are not used in the table.
The pool calculation is defined in
[`euro_optimality.py`](../../tools/offline-moves/euro_optimality.py).

## Other games and scope

DL2 uses native ROM prompts and is excluded from these calculated policy totals.
Other ROM revisions and Singe scripts have no results in this summary.
Optimal continuation after arbitrary mistakes or deaths is outside the current
proof scope; functional recovery checks do not establish that guarantee.

The complete source bundle is in [`strategies/`](strategies/), with generation
and proof instructions in the [offline tool guide](../../tools/offline-moves/README.md).
