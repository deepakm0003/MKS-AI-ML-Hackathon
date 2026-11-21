# Experiment report — champion vs challengers

All runs: same cleaned demand panel, 6 rolling cutoffs (2022-10 → 2025-03), 19-month horizon.
Minutes are wall-clock (c4 includes ~8 h of laptop sleep; C6, C9, seed_bag and origin_step1 ran in parallel on the 56-core server, which reproduces the champion exactly).

| Rank | Experiment | WAPE | Δ vs champion | Bias | MAE | 1–3 m | 4–6 m | 7–12 m | 13–19 m | Family-month | Total-month | Cutoffs won | Minutes | Verdict |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | c9c_keep_pull_forward | 0.2837 | -0.0060 | -2.8% | 13.43 | 0.278 | 0.274 | 0.281 | 0.293 | 7.3% | 5.1% | 5/6 | 38.0 | PROMOTE |
| 2 | c9b_keep_event_months | 0.2850 | -0.0047 | -3.5% | 13.49 | 0.275 | 0.278 | 0.285 | 0.293 | 7.9% | 5.7% | 5/6 | 37.6 | PROMOTE |
| 3 | c9a_no_training_exclusions | 0.2864 | -0.0033 | -2.9% | 13.55 | 0.274 | 0.280 | 0.288 | 0.293 | 7.8% | 5.2% | 4/6 | 37.8 | reject: won 67% of cutoffs, worst -0.0048 |
| 4 | c8_blend_cross_catboost | 0.2880 | -0.0017 | -2.6% | 13.62 | 0.282 | 0.277 | 0.285 | 0.297 | 7.2% | 4.9% | 4/6 | 0.0 | reject: gain +0.0017; won 67% of cutoffs, worst -0.0026 |
| 5 | c4_seed_bag_cross | 0.2883 | -0.0014 | -3.1% | 13.64 | 0.284 | 0.278 | 0.286 | 0.296 | 7.7% | 5.6% | 5/6 | 608.6 | reject: gain +0.0014 |
| 6 | cross_series | 0.2884 | -0.0013 | -3.4% | 13.65 | 0.284 | 0.278 | 0.286 | 0.297 | 7.6% | 5.6% | 5/6 | 13.1 | reject: gain +0.0013 |
| 7 | c7_blend_lgb_catboost | 0.2888 | -0.0009 | -2.5% | 13.67 | 0.282 | 0.277 | 0.286 | 0.299 | 7.2% | 4.8% | 4/6 | 0.0 | reject: gain +0.0009; won 67% of cutoffs, worst -0.0028 |
| 8 | c1_growth | 0.2890 | -0.0007 | -3.2% | 13.67 | 0.285 | 0.279 | 0.286 | 0.298 | 7.7% | 5.2% | 3/6 | 8.8 | reject: gain +0.0007; won 50% of cutoffs, worst -0.0012 |
| 9 | seed_bag | 0.2893 | -0.0004 | -2.7% | 13.69 | 0.285 | 0.279 | 0.286 | 0.298 | 7.6% | 5.3% | 5/6 | 31.6 | reject: gain +0.0004 |
| 10 | origin_step1 | 0.2896 | -0.0001 | -2.8% | 13.70 | 0.284 | 0.278 | 0.287 | 0.299 | 7.7% | 5.4% | 3/6 | 28.2 | reject: gain +0.0001; won 50% of cutoffs, worst -0.0014 |
| 11 | champion | 0.2897 | +0.0000 | -3.0% | 13.71 | 0.284 | 0.279 | 0.287 | 0.299 | 7.6% | 5.4% | — | 12.2 | CHAMPION |
| 12 | c3_interm_features | 0.2903 | +0.0006 | -2.5% | 13.73 | 0.285 | 0.280 | 0.288 | 0.299 | 7.8% | 5.4% | 3/6 | 30.9 | reject: gain -0.0006; won 50% of cutoffs, worst -0.0039 |
| 13 | c9d_keep_event_windows | 0.2920 | +0.0023 | -3.5% | 13.82 | 0.286 | 0.284 | 0.292 | 0.298 | 8.2% | 5.9% | 2/6 | 38.0 | reject: gain -0.0023; horizon bucket -0.0054; won 33% of cutoffs, worst -0.0100; segment Asia Pacific +0.0064 |
| 14 | c5_catboost | 0.2925 | +0.0028 | -2.1% | 13.84 | 0.285 | 0.280 | 0.290 | 0.303 | 7.0% | 4.4% | 2/6 | 49.0 | reject: gain -0.0028; horizon bucket -0.0042; won 33% of cutoffs, worst -0.0097; segment Chassis & Structural +0.0058 |
| 15 | c6_no_ev_level | 0.2937 | +0.0040 | -3.0% | 13.90 | 0.286 | 0.282 | 0.290 | 0.305 | 8.0% | 5.7% | 0/6 | 23.0 | reject: gain -0.0040; horizon bucket -0.0059; won 0% of cutoffs, worst -0.0093; segment Electrical Assemblies +0.0066 |
| 16 | c3_hurdle | 0.2947 | +0.0050 | +0.3% | 13.94 | 0.288 | 0.281 | 0.292 | 0.306 | 7.5% | 4.9% | 1/6 | 19.4 | reject: gain -0.0050; horizon bucket -0.0066; won 17% of cutoffs, worst -0.0118; segment Electrical Assemblies +0.0142 |
| 17 | c2_horizon_split | 0.2952 | +0.0055 | -3.2% | 13.97 | 0.281 | 0.277 | 0.297 | 0.307 | 8.6% | 6.2% | 0/6 | 10.0 | reject: gain -0.0055; horizon bucket -0.0108; won 0% of cutoffs, worst -0.0106; segment Electrical Assemblies +0.0094 |
| 18 | c3_hurdle_interm | 0.2956 | +0.0059 | +0.7% | 13.99 | 0.289 | 0.283 | 0.294 | 0.305 | 7.8% | 4.9% | 1/6 | 51.4 | reject: gain -0.0059; horizon bucket -0.0073; won 17% of cutoffs, worst -0.0163; segment Electrical Assemblies +0.0141 |
| 19 | no_macro | 0.3019 | +0.0122 | -2.1% | 14.29 | 0.283 | 0.286 | 0.305 | 0.314 | 10.8% | 8.9% | 2/6 | 7.8 | reject: gain -0.0122; horizon bucket -0.0183; won 33% of cutoffs, worst -0.0463; segment Electrical Assemblies +0.0225 |

## Where each challenger gains or loses (Δ WAPE vs champion; negative = better)

### Family

|                          |   c9c_keep_pull_forward |   c9b_keep_event_months |   c9a_no_training_exclusions |   c8_blend_cross_catboost |   c4_seed_bag_cross |   cross_series |   c7_blend_lgb_catboost |   c1_growth |   seed_bag |   origin_step1 |   c3_interm_features |   c9d_keep_event_windows |   c5_catboost |   c6_no_ev_level |   c3_hurdle |   c2_horizon_split |   c3_hurdle_interm |   no_macro |
|:-------------------------|------------------------:|------------------------:|-----------------------------:|--------------------------:|--------------------:|---------------:|------------------------:|------------:|-----------:|---------------:|---------------------:|-------------------------:|--------------:|-----------------:|------------:|-------------------:|-------------------:|-----------:|
| Brake & Safety Systems   |                 -0.0039 |                 -0.0002 |                       0.002  |                   -0.0012 |             -0.0003 |         0.0007 |                 -0.0008 |     -0.0013 |    -0.0006 |        -0      |              -0.0002 |                   0.0058 |        0.0026 |           0.0051 |      0.0004 |             0.0012 |             0.0017 |     0.0057 |
| Chassis & Structural     |                 -0.0064 |                 -0.0033 |                      -0.0025 |                    0.0001 |             -0.0012 |        -0.0006 |                  0.0008 |     -0.0004 |    -0.001  |        -0.0001 |               0.0002 |                   0.0047 |        0.0058 |           0.0042 |     -0.0004 |             0.008  |            -0.0004 |     0.0187 |
| Electrical Assemblies    |                 -0.0087 |                 -0.0083 |                      -0.0078 |                   -0.0027 |             -0.0034 |        -0.0037 |                 -0.001  |     -0.0001 |    -0.0002 |        -0.0016 |               0.0023 |                  -0.0006 |        0.0033 |           0.0066 |      0.0142 |             0.0094 |             0.0141 |     0.0225 |
| Hydraulic Systems        |                 -0.0064 |                 -0.008  |                      -0.0065 |                   -0.0033 |             -0.0023 |        -0.0034 |                 -0.0018 |     -0.0013 |    -0.0003 |        -0.0007 |               0.0008 |                  -0.001  |        0.0003 |           0.0004 |      0.0099 |             0.0077 |             0.0138 |     0.0143 |
| Powertrain Components    |                 -0.0053 |                 -0.0043 |                      -0.0013 |                   -0.0023 |             -0.0013 |        -0.0014 |                 -0.0014 |     -0.0015 |    -0.0004 |         0.0007 |               0.0005 |                   0.0029 |        0.0015 |           0.0022 |      0.0055 |             0.0031 |             0.006  |     0.0078 |
| Precision Machined Parts |                 -0.0058 |                 -0.0078 |                      -0.0065 |                   -0.0019 |             -0.0016 |        -0.002  |                 -0.0011 |     -0.0008 |    -0.0002 |        -0.0003 |               0.0006 |                  -0.0007 |        0.0027 |           0.003  |      0.0051 |             0.0065 |             0.0068 |     0.0104 |
| Thermal Management       |                 -0.0067 |                 -0.0034 |                      -0.0035 |                   -0.0017 |             -0.0009 |        -0.0001 |                 -0.0012 |      0.0004 |    -0.0001 |         0.0005 |               0.0006 |                   0.003  |        0.0028 |           0.0063 |      0.0052 |             0.0052 |             0.0047 |     0.0117 |

### Region

|                      |   c9c_keep_pull_forward |   c9b_keep_event_months |   c9a_no_training_exclusions |   c8_blend_cross_catboost |   c4_seed_bag_cross |   cross_series |   c7_blend_lgb_catboost |   c1_growth |   seed_bag |   origin_step1 |   c3_interm_features |   c9d_keep_event_windows |   c5_catboost |   c6_no_ev_level |   c3_hurdle |   c2_horizon_split |   c3_hurdle_interm |   no_macro |
|:---------------------|------------------------:|------------------------:|-----------------------------:|--------------------------:|--------------------:|---------------:|------------------------:|------------:|-----------:|---------------:|---------------------:|-------------------------:|--------------:|-----------------:|------------:|-------------------:|-------------------:|-----------:|
| Asia Pacific         |                 -0.0043 |                 -0.0011 |                      -0      |                   -0.0021 |             -0.0019 |        -0.0017 |                 -0.0009 |     -0.0005 |    -0.0005 |         0.0005 |               0.0008 |                   0.0064 |        0.0025 |           0.0042 |      0.0038 |             0.0065 |             0.0049 |     0.0139 |
| Europe               |                 -0.0051 |                 -0.0038 |                      -0.0015 |                   -0.0016 |             -0.0005 |        -0.0006 |                 -0.001  |     -0.0011 |    -0.0003 |        -0.0001 |               0.0012 |                   0.0009 |        0.0024 |           0.0044 |      0.0058 |             0.0063 |             0.0068 |     0.0129 |
| India                |                 -0.0037 |                  0      |                       0.0021 |                   -0.0014 |             -0.0024 |        -0.0019 |                 -0.0002 |     -0.0007 |    -0.0006 |        -0.0007 |               0.0002 |                   0.0051 |        0.0039 |           0.0034 |      0.0036 |             0.0046 |             0.0044 |     0.0132 |
| Latin America        |                 -0.0059 |                 -0.0062 |                      -0.006  |                   -0.0005 |             -0.0006 |        -0.0006 |                 -0.0001 |      0.0004 |    -0.0001 |        -0.0002 |               0.0005 |                   0.0027 |        0.0039 |           0.0041 |      0.0059 |             0.0031 |             0.007  |     0.0082 |
| Middle East & Africa |                 -0.0173 |                 -0.0208 |                      -0.02   |                   -0.0026 |             -0.0006 |        -0.0005 |                 -0.0024 |     -0.0004 |    -0.0006 |         0.0001 |               0.0005 |                  -0.0044 |        0.0029 |           0.004  |      0.0045 |             0.0091 |             0.005  |     0.0186 |
| North America        |                 -0.0053 |                 -0.0044 |                      -0.003  |                   -0.0025 |             -0.002  |        -0.0018 |                 -0.0014 |     -0.0017 |    -0.0005 |        -0.0002 |               0.0001 |                   0.0001 |        0.0014 |           0.004  |      0.0058 |             0.005  |             0.0069 |     0.0094 |

### Lifecycle

|                 |   c9c_keep_pull_forward |   c9b_keep_event_months |   c9a_no_training_exclusions |   c8_blend_cross_catboost |   c4_seed_bag_cross |   cross_series |   c7_blend_lgb_catboost |   c1_growth |   seed_bag |   origin_step1 |   c3_interm_features |   c9d_keep_event_windows |   c5_catboost |   c6_no_ev_level |   c3_hurdle |   c2_horizon_split |   c3_hurdle_interm |   no_macro |
|:----------------|------------------------:|------------------------:|-----------------------------:|--------------------------:|--------------------:|---------------:|------------------------:|------------:|-----------:|---------------:|---------------------:|-------------------------:|--------------:|-----------------:|------------:|-------------------:|-------------------:|-----------:|
| approaching EOL |                 -0.0034 |                 -0.0067 |                      -0.0105 |                   -0.0013 |              0.0005 |         0.0001 |                 -0.0014 |      0.0009 |     0.0013 |        -0.0002 |               0.0023 |                  -0.002  |        0.0004 |           0.0079 |      0.005  |             0.0066 |             0.0077 |    -0.0053 |
| declining       |                 -0.0019 |                  0.0058 |                       0.008  |                   -0.0022 |             -0.0014 |        -0.0013 |                 -0.0009 |     -0.0019 |    -0.0002 |        -0.0005 |               0.0008 |                   0.0114 |        0.0034 |           0.0033 |      0.0064 |             0.0038 |             0.0089 |     0.0028 |
| established     |                 -0.0044 |                 -0.0035 |                      -0.0023 |                   -0.0015 |             -0.0015 |        -0.0014 |                 -0.0007 |     -0.0006 |    -0.0004 |         0.0003 |               0.0005 |                   0.0017 |        0.0025 |           0.0042 |      0.0049 |             0.0056 |             0.0058 |     0.0144 |
| new (<24m)      |                 -0.0234 |                 -0.0283 |                      -0.0269 |                   -0.0027 |             -0.0006 |        -0      |                 -0.0024 |     -0.0003 |    -0.0007 |        -0.0027 |               0.0003 |                  -0.0057 |        0.0042 |           0.0033 |      0.0033 |             0.0071 |             0.0022 |     0.0107 |

### Demand class

|              |   c9c_keep_pull_forward |   c9b_keep_event_months |   c9a_no_training_exclusions |   c8_blend_cross_catboost |   c4_seed_bag_cross |   cross_series |   c7_blend_lgb_catboost |   c1_growth |   seed_bag |   origin_step1 |   c3_interm_features |   c9d_keep_event_windows |   c5_catboost |   c6_no_ev_level |   c3_hurdle |   c2_horizon_split |   c3_hurdle_interm |   no_macro |
|:-------------|------------------------:|------------------------:|-----------------------------:|--------------------------:|--------------------:|---------------:|------------------------:|------------:|-----------:|---------------:|---------------------:|-------------------------:|--------------:|-----------------:|------------:|-------------------:|-------------------:|-----------:|
| erratic      |                 -0.0043 |                 -0.0017 |                      -0.0004 |                   -0.0025 |             -0.0016 |        -0.0018 |                 -0.0015 |      0.0003 |    -0.0001 |         0.0006 |               0.0007 |                   0.0013 |        0.0016 |           0.0048 |      0.0061 |             0.0034 |             0.0074 |     0.0056 |
| intermittent |                 -0.0117 |                 -0.011  |                      -0.0097 |                    0.0003 |             -0.002  |        -0.0016 |                  0.0014 |     -0.0004 |    -0.0007 |        -0.0003 |               0.0003 |                   0.0042 |        0.0088 |           0.0017 |      0.0069 |             0.0086 |             0.0076 |     0.0149 |
| lumpy        |                 -0.0119 |                 -0.0129 |                      -0.0125 |                    0.001  |             -0.0038 |        -0.0049 |                  0.0027 |     -0.0038 |    -0.0038 |        -0.0017 |              -0.0044 |                  -0.0026 |        0.0094 |          -0.007  |     -0.0105 |            -0.0045 |            -0.0056 |     0.011  |
| smooth       |                 -0.004  |                 -0.0025 |                      -0.0011 |                   -0.0025 |             -0.0012 |        -0.0011 |                 -0.0017 |     -0.0008 |    -0.0003 |        -0.0001 |               0.0007 |                   0.0017 |        0.0007 |           0.0049 |      0.0043 |             0.0046 |             0.0053 |     0.0115 |

### Volume

|         |   c9c_keep_pull_forward |   c9b_keep_event_months |   c9a_no_training_exclusions |   c8_blend_cross_catboost |   c4_seed_bag_cross |   cross_series |   c7_blend_lgb_catboost |   c1_growth |   seed_bag |   origin_step1 |   c3_interm_features |   c9d_keep_event_windows |   c5_catboost |   c6_no_ev_level |   c3_hurdle |   c2_horizon_split |   c3_hurdle_interm |   no_macro |
|:--------|------------------------:|------------------------:|-----------------------------:|--------------------------:|--------------------:|---------------:|------------------------:|------------:|-----------:|---------------:|---------------------:|-------------------------:|--------------:|-----------------:|------------:|-------------------:|-------------------:|-----------:|
| Q1 low  |                 -0.0164 |                 -0.0203 |                      -0.0195 |                   -0.0021 |              0.0009 |         0.0008 |                 -0.0024 |     -0.0006 |    -0.0002 |        -0.0015 |               0.002  |                  -0.0052 |        0.0019 |           0.0047 |     -0.0002 |             0.0081 |             0.0002 |     0.0202 |
| Q2      |                 -0.01   |                 -0.0087 |                      -0.0078 |                   -0.0023 |             -0.0016 |        -0.0012 |                 -0.0014 |     -0.0003 |    -0.0007 |        -0.0007 |               0.0007 |                   0.0028 |        0.0017 |           0.0024 |      0.0056 |             0.0059 |             0.0054 |     0.0161 |
| Q3      |                 -0.0052 |                 -0.0034 |                      -0.0018 |                   -0.0011 |             -0.001  |        -0.001  |                 -0.0003 |     -0.0003 |    -0.0001 |         0      |               0.0013 |                   0.004  |        0.0037 |           0.0038 |      0.0066 |             0.0057 |             0.0077 |     0.0141 |
| Q4      |                 -0.0037 |                 -0.0016 |                      -0.0001 |                   -0.0012 |             -0.0011 |        -0.0013 |                 -0.0004 |     -0.0002 |    -0      |         0.0003 |               0.0008 |                   0.0026 |        0.0032 |           0.0043 |      0.0059 |             0.0059 |             0.0075 |     0.0114 |
| Q5 high |                 -0.004  |                 -0.0021 |                      -0.0007 |                   -0.0021 |             -0.0022 |        -0.0018 |                 -0.001  |     -0.0014 |    -0.0007 |         0      |              -0.0003 |                   0.003  |        0.0026 |           0.0044 |      0.0045 |             0.0045 |             0.0055 |     0.0089 |

### Bias by family (the champion's known weakness: vehicle-build families)

|                          |   champion |   c9c_keep_pull_forward |   c9b_keep_event_months |   c9a_no_training_exclusions |   c8_blend_cross_catboost |   c4_seed_bag_cross |   cross_series |   c7_blend_lgb_catboost |   c1_growth |   seed_bag |   origin_step1 |   c3_interm_features |   c9d_keep_event_windows |   c5_catboost |   c6_no_ev_level |   c3_hurdle |   c2_horizon_split |   c3_hurdle_interm |   no_macro |
|:-------------------------|-----------:|------------------------:|------------------------:|-----------------------------:|--------------------------:|--------------------:|---------------:|------------------------:|------------:|-----------:|---------------:|---------------------:|-------------------------:|--------------:|-----------------:|------------:|-------------------:|-------------------:|-----------:|
| Brake & Safety Systems   |       -5   |                    -4.4 |                    -5.7 |                         -5   |                      -4.7 |                -4.8 |           -4.8 |                    -4.8 |        -3.9 |       -4.7 |           -4.6 |                 -4.4 |                     -5.6 |          -4.6 |             -4.2 |        -2.1 |               -6   |               -1.5 |       -4   |
| Chassis & Structural     |       -8.3 |                    -7.2 |                    -8.7 |                         -8.5 |                      -8   |                -8.1 |           -8.4 |                    -8.1 |        -8.9 |       -7.9 |           -7.9 |                 -8.1 |                     -9.3 |          -7.9 |             -8.9 |        -5.4 |               -8.9 |               -5.3 |       -6   |
| Electrical Assemblies    |        0.9 |                     0.3 |                     0.4 |                          0.8 |                       1.6 |                 0.4 |           -0.1 |                     1.9 |         1.9 |        1.2 |            0.7 |                  1.8 |                      0.8 |           2.8 |              1.2 |         5.5 |                1.7 |                5.7 |        2.9 |
| Hydraulic Systems        |        0.5 |                    -0.1 |                     0.2 |                          0.7 |                       0.3 |                -0.3 |           -1   |                     0.7 |         1.4 |        0.6 |            0.4 |                  1   |                      0.3 |           0.9 |              0.3 |         4.2 |                0.8 |                5.1 |        1   |
| Powertrain Components    |        0.8 |                     0.9 |                     0.7 |                          1.5 |                       1.2 |                 0   |           -0.2 |                     1.6 |        -0.2 |        1   |            1   |                  1.2 |                      0.6 |           2.4 |              0.1 |         3.8 |                1.1 |                4.1 |        0.5 |
| Precision Machined Parts |       -1.3 |                    -1   |                    -1.5 |                         -0.7 |                      -0.9 |                -2   |           -2.3 |                    -0.5 |        -2.1 |       -1.1 |           -1.4 |                 -0.9 |                     -1.7 |           0.3 |             -1.5 |         1.8 |               -1.1 |                2.4 |       -1.1 |
| Thermal Management       |       -5.8 |                    -6.2 |                    -7.2 |                         -6.6 |                      -5   |                -4.7 |           -5   |                    -5.5 |        -7.3 |       -5.6 |           -5.5 |                 -5.3 |                     -6.8 |          -5.3 |             -5.3 |        -2.4 |               -6.7 |               -2   |       -5.1 |

## Aggregate accuracy (family-month and company-month WAPE)

Series-level WAPE decides promotion; the aggregate columns show which models planners would trust for family and company totals.

| experiment                 |   WAPE |   WAPE_family_month |   WAPE_total_month |
|:---------------------------|-------:|--------------------:|-------------------:|
| c5_catboost                |  29.25 |                7.04 |               4.44 |
| c7_blend_lgb_catboost      |  28.88 |                7.21 |               4.8  |
| c8_blend_cross_catboost    |  28.8  |                7.17 |               4.87 |
| c3_hurdle                  |  29.47 |                7.54 |               4.9  |
| c3_hurdle_interm           |  29.56 |                7.76 |               4.92 |
| c9c_keep_pull_forward      |  28.37 |                7.33 |               5.15 |
| c9a_no_training_exclusions |  28.64 |                7.84 |               5.24 |
| c1_growth                  |  28.9  |                7.71 |               5.24 |
| seed_bag                   |  28.93 |                7.63 |               5.33 |
| champion                   |  28.97 |                7.65 |               5.36 |
| c3_interm_features         |  29.03 |                7.78 |               5.39 |
| origin_step1               |  28.96 |                7.71 |               5.42 |
| c4_seed_bag_cross          |  28.83 |                7.66 |               5.56 |
| cross_series               |  28.84 |                7.61 |               5.58 |
| c9b_keep_event_months      |  28.5  |                7.93 |               5.68 |
| c6_no_ev_level             |  29.37 |                7.95 |               5.73 |
| c9d_keep_event_windows     |  29.2  |                8.16 |               5.94 |
| c2_horizon_split           |  29.52 |                8.59 |               6.16 |
| no_macro                   |  30.19 |               10.82 |               8.93 |

## Cleaning sensitivity (3 cutoffs, common yardstick of untouched months)

| Variant                | Description                                                                                 |   rows |   WAPE |    Bias |   WAPE_vs_baseline |
|:-----------------------|:--------------------------------------------------------------------------------------------|-------:|-------:|--------:|-------------------:|
| baseline               | champion cleaning (stockout recovery, DiD allocation uplift, event exclusions)              | 164708 | 0.2779 | -0.0367 |             0      |
| no_stockout_recovery   | target = shipped units everywhere: no stockout file, backorder netting or allocation uplift | 164708 | 0.2822 | -0.0485 |             0.0043 |
| no_allocation_uplift   | stockout file and backorder netting kept; chip-shortage months left at shipped units        | 164708 | 0.2781 | -0.0358 |             0.0002 |
| exclude_stockouts      | stockout months dropped from training (weight 0, causal fill) instead of recovered          | 164708 | 0.2815 | -0.0375 |             0.0036 |
| no_training_exclusions | event windows, price pull-forward and one-off orders kept as training targets               | 164708 | 0.2747 | -0.0121 |            -0.0032 |

## Cleaning sensitivity - final 19-month forecast

| Variant                |   Total_19m |   Total_19m_vs_base_pct |
|:-----------------------|------------:|------------------------:|
| baseline               | 2.83578e+06 |                    0    |
| no_stockout_recovery   | 2.85034e+06 |                    0.51 |
| no_allocation_uplift   | 2.83697e+06 |                    0.04 |
| exclude_stockouts      | 2.84863e+06 |                    0.45 |
| no_training_exclusions | 2.82184e+06 |                   -0.49 |

## Post-hoc corrections (walk-forward WAPE)

| cutoff   |   model_mean |   rounded_to_integer |   median_P50 |   global_bias_correction |   family_bias_correction |
|:---------|-------------:|---------------------:|-------------:|-------------------------:|-------------------------:|
| 2023-04  |       0.2903 |               0.2902 |       0.301  |                   0.2896 |                   0.2915 |
| 2023-10  |       0.2798 |               0.2797 |       0.2833 |                   0.2798 |                   0.2831 |
| 2024-04  |       0.265  |               0.2648 |       0.2691 |                   0.2644 |                   0.2672 |
| 2024-10  |       0.2721 |               0.2719 |       0.2716 |                   0.275  |                   0.275  |
| 2025-03  |       0.2716 |               0.2714 |       0.2708 |                   0.2754 |                   0.2754 |
| mean     |       0.2758 |               0.2756 |       0.2792 |                   0.2768 |                   0.2784 |

## Interval calibration (leave-one-cutoff-out)

| Method               |   Coverage_P10_P90 |   Worst_segment_coverage |   Mean_abs_gap_to_80pct |   Band_width_vs_forecast |   Pinball_P10 |   Pinball_P90 |
|:---------------------|-------------------:|-------------------------:|------------------------:|-------------------------:|--------------:|--------------:|
| pooled (stage 4)     |             0.8248 |                   0.7471 |                  0.0291 |                   0.8923 |        2.589  |        3.8455 |
| stratified (Phase D) |             0.8219 |                   0.79   |                  0.0225 |                   0.8887 |        2.5724 |        3.8247 |

## Series reliability tiers (champion)

| Tier         |   Series |   Volume_share |   Median_WAPE |
|:-------------|---------:|---------------:|--------------:|
| A reliable   |      861 |          0.374 |         0.222 |
| B usable     |     1824 |          0.562 |         0.303 |
| C weak       |      316 |          0.056 |         0.443 |
| D unreliable |       46 |          0.009 |         0.69  |

## Decision

**Promoted: `c9c_keep_pull_forward`** - the champion's model, features and parameters, unchanged,
trained on the price-announcement months (Nov 2022 - Feb 2023) instead of excluding them.
The demand target is identical, so the comparison is like for like.

| | Champion | C9c | Change |
|---|---:|---:|---:|
| WAPE (6 cutoffs) | 0.2897 | **0.2837** | −0.0060 (bar: 0.002) |
| Cutoffs better / equal / worse | | 5 / 1 / 0 | 2022-10 is identical: the months come after that cutoff |
| Bias | −3.0% | −2.8% | improved |
| Family-month WAPE | 7.65% | 7.33% | improved |
| Company-month WAPE | 5.36% | 5.15% | improved |
| New series (< 24 m) | 0.391 | 0.368 | largest gain |
| Middle East & Africa | 0.379 | 0.362 | second largest gain |

All six promotion criteria hold: every horizon bucket, family, region and lifecycle segment
improves; no cutoff gets worse; features are unchanged, so the leakage audit still applies;
the test suite passes. C9c is also better in every calendar month of the post-2022 backtests,
including January and February of years without a price rise, so it is not fitting a one-off.

**Why:** the price-rise rule removed four whole months (every series) from the training
target and replaced them with a trailing mean in the lag features. The early-buying and
payback effect it guarded against is about ±10%; losing the four most recent real months
cost more. The cleaning-sensitivity test found this first (keeping all event months: −0.0032
on a common yardstick), and the 6-cutoff C9 runs isolated it to the pull-forward months -
keeping the COVID-lockdown and strike months instead (C9d) makes the model worse.

## What was rejected, and what it taught us

* **Near misses (gain 0.001–0.002):** cross-series features (C4 0.2883, better on 5/6 cutoffs),
  seed bagging (0.2893, 5/6), and the CatBoost blends (C8 0.2880, C7 0.2888). Consistent but
  below the bar on their own.
* **CatBoost (C5)** loses at series level (0.2925) but has the **lowest company-month error of
  all models (4.4%)** - the right choice if planners judge mainly on totals.
* **Clear losers:** horizon-split models (C2), the hurdle models (C3b/c), dropping the EV index
  (C6: the EV index carries real signal, not just a trend), dropping macro features entirely.
* **Cleaning decisions confirmed:** stockout recovery is right (without it: +0.0043 WAPE,
  bias −4.9%); recovering stockouts beats dropping them (+0.0036); the chip-shortage uplift is
  neutral. Each cleaning variant moves the 19-month forecast by at most ±0.5%.
* **No post-hoc fixes:** median (P50) instead of mean, global or family bias correction all
  lose walk-forward - the bias is not stable enough over time to correct after the fact.

## Recommendation for the next milestone

1. **Rebase the champion on C9c** (`config/experiments.yaml`) and re-run the near misses on
   top of it - cross-series + seed bagging and the CatBoost blend. Their gains were measured
   against the old champion and may now stack past the promotion bar.
2. **Add an explicit price-announcement feature** so a future price rise is modelled from the
   events calendar rather than inferred from month-of-year (C9c's January bias is −3.8% vs
   −3.0%).
3. **Remaining bias** is concentrated in Chassis (−7.2%), Thermal (−6.2%), new series (−6.4%)
   and Middle East & Africa (−4.9%); the family-specific macro sensitivity of C1 is the most
   promising lever on top of C9c.
4. **Build the dashboard** on the frozen data contract (`contracts/data_contract.yaml`, API in
   `api/app.py`) - the backend no longer changes underneath it.
