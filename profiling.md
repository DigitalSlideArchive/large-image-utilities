# Python Profiling

## cProfiler

- Deterministic.
- Most viewing tools are summaries. 
- Standard modules.

### Command

```
python -m cProfile -o cprofile.out lisource_compare TCGA-AA.svs --encoding=PNG
```

### Results

```
import pstats
s = pstats.Stats('cprofile.out')
s.sort_stats('cumulative')
s.print_stats('large_image', 15)
```

### Example

```
ncalls  tottime  percall  cumtime  percall filename:lineno(function)
  2779/47    0.023    0.000   24.817    0.528 large_image/cache_util/cache.py:73(wrapper)
13354/6306    0.022    0.000   23.367    0.004 large_image/tilesource/tiledict.py:150(__getitem__)
    16    0.011    0.001   23.173    1.448 large_image/tilesource/base.py:877(histogram)
   418    0.102    0.000   20.569    0.049 large_image/tilesource/tiledict.py:115(_retileTile)
    62   12.543    0.202   12.561    0.203 sources/mapnik/large_image_source_mapnik/__init__.py:324(getTile)
   386    0.006    0.000    5.485    0.014 sources/gdal/large_image_source_gdal/__init__.py:763(getTile)
   802    0.003    0.000    1.577    0.002 large_image/tilesource/base.py:1272(_outputTile)
   678    0.042    0.000    1.540    0.002 large_image/tilesource/base.py:1245(_outputTileNumpyStyle)
   386    0.617    0.002    1.412    0.004 large_image/tilesource/base.py:1123(_applyStyle)
   114    0.004    0.000    1.264    0.011 sources/openslide/large_image_source_openslide/__init__.py:276(getTile)
    26    0.001    0.000    1.181    0.045 large_image/cache_util/cache.py:166(__call__)
     2    0.000    0.000    1.072    0.536 sources/bioformats/large_image_source_bioformats/__init__.py:170(__init__)
     1    0.000    0.000    1.070    1.070 large_image/tilesource/__init__.py:183(canReadList)
    13    0.000    0.000    1.070    0.082 large_image/tilesource/base.py:2526(canRead)
     5    0.000    0.000    0.959    0.192 large_image/tilesource/base.py:1596(getThumbnail)
```     

### Alternate result viewers

#### Snakeviz

Often fails for even short examples like this.

Need to use a utility to convert to valgrind or speedscope


## pprofile

- Deterministic or statistical sampling
- Line-level details
- Slow, but sampling results are good for long processes

### Command

#### Deterministic

```
python -m pprofile -o pprofile.out lisource_compare TCGA-AA.svs --encoding=PNG
```

#### Statistical

```
python -m pprofile -o pprofile_stats.out -s 0.001 lisource_compare TCGA-AA.svs --encoding=PNG
```

### Results

pprofile.out is a text file:

```
(call)|         1|   0.00334811|   0.00334811|  0.01%|# large_image/sources/mapnik/large_image_source_mapnik/__init__.py:293 addStyle
   381|         1|  6.19888e-06|  6.19888e-06|  0.00%|                if getattr(self, '_repeatLongitude', None):
   382|         0|            0|            0|  0.00%|                    self.addStyle(m, self._repeatLongitude, extent)
   383|         1|  3.57628e-06|  3.57628e-06|  0.00%|                self._mapnikMap = m
   384|         0|            0|            0|  0.00%|            else:
   385|        61|  0.000229597|  3.76389e-06|  0.00%|                m = self._mapnikMap
   386|        62|   0.00105166|  1.69623e-05|  0.00%|            m.zoom_to_box(mapnik.Box2d(xmin, ymin, xmax, ymax))
   387|        62|   0.00130343|  2.10231e-05|  0.00%|            img = mapnik.Image(self.tileWidth + overscan * 2, self.tileHeight + overscan * 2)
   388|        62|      12.5988|     0.203206| 31.34%|            mapnik.render(m, img)
   389|        62|    0.0036943|  5.95854e-05|  0.01%|            pilimg = PIL.Image.frombytes('RGBA', (img.width(), img.height()), img.tostring())
(call)|        62|    0.0177846|  0.000286848|  0.04%|# env/lib/python3.9/site-packages/PIL/Image.py:2673 frombytes
   390|        62|  0.000220776|   3.5609e-06|  0.00%|        if overscan:
   391|        62|   0.00130415|  2.10347e-05|  0.00%|            pilimg = pilimg.crop((1, 1, pilimg.width - overscan, pilimg.height - overscan))
```

To find the lines where more than 10% of the time was spent in a deterministic profile:
```
grep '\( [1-9]\|[1-9][0-9]\)\.[0-9][0-9]%' pprofile.out
```

To find the lines where more than 10,000 samples were taken in a statistical profile:
```
grep '|[ 0-9][ 0-9][ 0-9][ 0-9][ 0-9][0-9][0-9][0-9][0-9][0-9]|' pprofile.out
```


## viztracer

- Deterministic
- Good viewer, though limited in how many samples it can show
- Best viewer for multi-threaded

### Command

```
viztracer --tracer_entries 10000000 -o viztracer.json lisource_compare TCGA-AA.svs --encoding=PNG
```

### Results

```
vizviewer -s -p 8000 viztracer.json
```

Then open a web browser to port 8000.  You can run with the `--use_external_processor` flag to show more samples, but then the port doesn't seem configurable.


## py-spy

- Sampling
- Can connect to a running instance

### Command

#### Recorded

```
py-spy record --output pyspy.out -- lisource_compare TCGA-AA.svs --encoding=PNG
```

#### Live

```
sudo py-spy top --pid `pidof lisource_compare`
```

### Results

For the record mode, the results look like a flame chart.

Danger: top mode sometimes kills the parent process when disconnecting


## memray

- Tracks memory usage, not time
- Default is to look at the high-water mark.

### Command

```
memray run --output memrayout.bin --force lisource_compare TCGA-AA.svs --encoding=PNG
```

### Results

Interactive tree to investigate peak memory:

```
memray tree memrayout.bin
```

List the highest allocation lines:

```
memray summary memrayout.bin
```

See a distribution of allocations by binned logarithmic sizes

```
memray stats memrayout.bin
```
