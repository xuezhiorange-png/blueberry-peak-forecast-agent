# 云南气候分区候选研究 R2

推荐：kmeans，K=5；仅待评审候选，不是预设五分区。
38 个 YUNNAN_CORE 基地等权；1 个外省基地保留登记、不拟合。

## 冻结方法与选择规则

配置：`configs/climate_zone_r2.json`，在首次画像/聚类运行前写入。
主时段1991–2020；种子42；K-means n_init=20；Ward 欧氏距离；单线程数值运算。
紧凑特征：annual_mean_temperature_c, annual_precipitation_mm, annual_temperature_range_c, precipitation_seasonality, dewpoint_depression_c, annual_radiation_mj_m2, elevation_m。
按优先级排除 |Pearson r|≥0.9 的冗余变量：{"coldest_month_mean_temperature_c": "CORRELATED_WITH_HIGHER_PRIORITY_FEATURE", "monsoon_fraction": "CORRELATED_WITH_HIGHER_PRIORITY_FEATURE"}。
完整相关矩阵、各候选方差比和标准化参数保存在 candidate-study.json，不加面积权重。
温度为按日数加权的多年平均；降水/辐射为完整年累计的多年均值。
季节性为12个月降水气候值的总体SD/均值；暖季固定May–Oct，不声称农业季节阈值。

门槛：每组≥3基地、30次80%无放回重采样平均ARI≥0.75、坐标一致率≥0.9、
两方法ARI≥0.6。通过后等权秩综合 silhouette、DB、重采样、坐标一致率、
海拔/温度/降水组内方差比；不单看最高分。重采样拟合后用最近质心扩展至全38基地。
这不是置信区间或外部泛化证明。唯一通过预设门槛的候选为 K-means K=5。

| 方法 | K | 组大小 | Silhouette | CH | DB | 方法ARI | 重采样均值ARI | 坐标一致率 | 资格 |
|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| ward | 3 | [28, 5, 5] | 0.3718 | 15.019 | 0.9581 | 0.4947 | 0.6146 | 1.0000 | False |
| kmeans | 3 | [12, 21, 5] | 0.2742 | 15.195 | 1.2613 | 0.4947 | 0.6100 | 1.0000 | False |
| ward | 4 | [20, 5, 5, 8] | 0.2571 | 14.783 | 1.0336 | 0.9227 | 0.5718 | 1.0000 | False |
| kmeans | 4 | [19, 5, 8, 6] | 0.2635 | 15.097 | 1.0307 | 0.9227 | 0.6755 | 1.0000 | False |
| ward | 5 | [5, 8, 5, 8, 12] | 0.2816 | 14.642 | 1.1311 | 0.7497 | 0.7193 | 1.0000 | False |
| kmeans | 5 | [8, 4, 5, 15, 6] | 0.2885 | 14.731 | 1.0427 | 0.7497 | 0.7685 | 1.0000 | True |
| ward | 6 | [8, 4, 5, 8, 12, 1] | 0.2881 | 14.673 | 1.0033 | 0.8662 | 0.7844 | 1.0000 | False |
| kmeans | 6 | [4, 8, 6, 6, 13, 1] | 0.2885 | 14.751 | 0.9721 | 0.8662 | 0.7335 | 1.0000 | False |
| ward | 7 | [5, 4, 6, 8, 12, 1, 2] | 0.3173 | 14.832 | 0.9314 | 0.7894 | 0.8324 | 1.0000 | False |
| kmeans | 7 | [14, 6, 1, 2, 8, 4, 3] | 0.3309 | 15.424 | 0.8276 | 0.7894 | 0.8221 | 1.0000 | False |
| ward | 8 | [4, 12, 6, 8, 3, 1, 2, 2] | 0.3539 | 15.660 | 0.8441 | 0.8497 | 0.8530 | 1.0000 | False |
| kmeans | 8 | [6, 13, 3, 8, 1, 4, 2, 1] | 0.3178 | 15.539 | 0.8283 | 0.8497 | 0.8227 | 1.0000 | False |

## 稳定性与限制

推荐候选重采样最差ARI=0.4292，均值仅略高于门槛；
不能表述为强稳定或已批准分区。高K出现单例/小组，低K重采样不稳定。
1996–2025沿用K、特征、标准化方法和算法，不重新选K；标签以最大重叠匹配消除任意编号影响。
一致率=0.921053，变化基地：弥勒西三基地、富民款庄基地、大理巍山基地。
38/38在±0.01°八个偏移位置下候选区不变；这不证明CRS已确认或气候值完全不变。
最近质心是Ward外样本诊断规则，不伪装成Ward原生predict。
没有行政区特征/边界约束；簇允许地理不连续，地理范围和气候统计供人工解释性评审。

## 候选区画像

### Z1: 温度中位17.5°C / 年降水中位954mm / 海拔中位1376m

基地数：8；成员：弥勒巡检司基地、弥勒新哨基地、开远开心莓基地、建水阿朋基地、弥勒朋普基地、建水面甸基地、弥勒五山基地、建水岔科基地。

地理范围：{"latitude": [23.68, 24.24], "longitude": [102.94, 103.44]}。

- annual_mean_temperature_c: min/median/max = 16.735/17.515/18.519
- annual_precipitation_mm: min/median/max = 851.477/954.092/1170.327
- annual_radiation_mj_m2: min/median/max = 5744.364/5785.856/5807.506
- annual_temperature_range_c: min/median/max = 10.388/10.592/10.947
- coldest_month_mean_temperature_c: min/median/max = 10.531/11.197/12.236
- dewpoint_depression_c: min/median/max = 4.821/5.954/6.440
- elevation_m: min/median/max = 1142.000/1376.500/1640.000
- monsoon_fraction: min/median/max = 0.769/0.794/0.834
- precipitation_seasonality: min/median/max = 0.634/0.684/0.801
- warmest_month_mean_temperature_c: min/median/max = 20.929/21.797/22.768

近期30年映射保持：8/8。

代表基地（距区内温度中位值最近）：建水阿朋基地、弥勒朋普基地、弥勒巡检司基地。

- recent_drift_summary dewpoint_depression_c: min/median/max = -0.291/-0.170/-0.076
- recent_drift_summary precipitation_mm: min/median/max = -72.806/-57.547/-0.982
- recent_drift_summary radiation_mj_m2: min/median/max = -437.782/-431.927/-417.914
- recent_drift_summary temperature_c: min/median/max = 0.196/0.356/0.375
- ytd_2026_same_month_summary dewpoint_depression_c: min/median/max = -0.188/0.096/0.297
- ytd_2026_same_month_summary precipitation_mm: min/median/max = -42.641/-0.621/76.501
- ytd_2026_same_month_summary radiation_mj_m2: min/median/max = 13.861/34.227/53.108
- ytd_2026_same_month_summary temperature_c: min/median/max = 0.432/0.618/0.705

### Z2: 温度中位14.6°C / 年降水中位1860mm / 海拔中位1703m

基地数：4；成员：保山由旺基地、腾冲曲石基地、腾冲中和基地、保山杨柳基地。

地理范围：{"latitude": [24.88, 25.2], "longitude": [98.41, 99.1]}。

- annual_mean_temperature_c: min/median/max = 13.663/14.636/15.799
- annual_precipitation_mm: min/median/max = 1457.328/1859.909/2197.925
- annual_radiation_mj_m2: min/median/max = 5656.892/5757.798/5841.803
- annual_temperature_range_c: min/median/max = 9.571/9.926/10.574
- coldest_month_mean_temperature_c: min/median/max = 7.435/8.677/9.884
- dewpoint_depression_c: min/median/max = 3.465/4.371/5.292
- elevation_m: min/median/max = 1499.000/1703.000/2155.000
- monsoon_fraction: min/median/max = 0.796/0.812/0.830
- precipitation_seasonality: min/median/max = 0.697/0.749/0.813
- warmest_month_mean_temperature_c: min/median/max = 18.009/18.547/19.567

近期30年映射保持：4/4。

代表基地（距区内温度中位值最近）：腾冲曲石基地、保山由旺基地、腾冲中和基地。

- recent_drift_summary dewpoint_depression_c: min/median/max = 0.153/0.173/0.268
- recent_drift_summary precipitation_mm: min/median/max = -483.554/-297.556/-248.978
- recent_drift_summary radiation_mj_m2: min/median/max = -302.634/-283.711/-257.298
- recent_drift_summary temperature_c: min/median/max = 0.382/0.610/0.656
- ytd_2026_same_month_summary dewpoint_depression_c: min/median/max = -0.289/0.079/0.238
- ytd_2026_same_month_summary precipitation_mm: min/median/max = -87.955/-72.619/-15.626
- ytd_2026_same_month_summary radiation_mj_m2: min/median/max = -41.185/-32.463/-27.970
- ytd_2026_same_month_summary temperature_c: min/median/max = 0.150/0.336/0.426

### Z3: 温度中位19.2°C / 年降水中位1742mm / 海拔中位949m

基地数：5；成员：澜沧东回基地、元江甘庄基地、版纳勐旺基地、腾冲德宏基地、澜沧上允基地。

地理范围：{"latitude": [22.41, 24.59], "longitude": [97.86, 101.95]}。

- annual_mean_temperature_c: min/median/max = 19.112/19.198/21.992
- annual_precipitation_mm: min/median/max = 1587.257/1741.529/2765.285
- annual_radiation_mj_m2: min/median/max = 5599.198/5868.394/6124.402
- annual_temperature_range_c: min/median/max = 7.813/8.071/8.703
- coldest_month_mean_temperature_c: min/median/max = 13.845/14.261/16.476
- dewpoint_depression_c: min/median/max = 4.209/5.215/5.570
- elevation_m: min/median/max = 806.000/949.000/1410.000
- monsoon_fraction: min/median/max = 0.730/0.843/0.868
- precipitation_seasonality: min/median/max = 0.556/0.756/0.899
- warmest_month_mean_temperature_c: min/median/max = 21.900/22.096/25.179

近期30年映射保持：5/5。

代表基地（距区内温度中位值最近）：腾冲德宏基地、澜沧上允基地、版纳勐旺基地。

- recent_drift_summary dewpoint_depression_c: min/median/max = -0.279/0.034/0.398
- recent_drift_summary precipitation_mm: min/median/max = -706.816/-224.111/-176.681
- recent_drift_summary radiation_mj_m2: min/median/max = -379.310/-336.110/-210.569
- recent_drift_summary temperature_c: min/median/max = 0.061/0.449/0.660
- ytd_2026_same_month_summary dewpoint_depression_c: min/median/max = -0.956/-0.126/0.012
- ytd_2026_same_month_summary precipitation_mm: min/median/max = -27.205/124.316/263.140
- ytd_2026_same_month_summary radiation_mj_m2: min/median/max = -71.616/-63.810/24.064
- ytd_2026_same_month_summary temperature_c: min/median/max = -0.383/0.104/0.502

### Z4: 温度中位16.1°C / 年降水中位1192mm / 海拔中位1521m

基地数：15；成员：广南旧莫基地、丘北曰者基地、砚山黑鱼洞基地、砚山阿猛基地、弥勒西三基地、丘北双龙营二基地、砚山回龙基地、丘北双龙营一基地、砚山炭房基地、砚山平远基地、泸西基地、丘北天星基地、曲靖潇湘基地、砚山维摩基地、砚山盘龙基地。

地理范围：{"latitude": [23.51, 25.43], "longitude": [103.48, 104.97]}。

- annual_mean_temperature_c: min/median/max = 13.604/16.092/17.103
- annual_precipitation_mm: min/median/max = 1027.332/1191.601/1462.241
- annual_radiation_mj_m2: min/median/max = 5262.501/5594.952/5780.341
- annual_temperature_range_c: min/median/max = 11.281/11.464/13.040
- coldest_month_mean_temperature_c: min/median/max = 6.793/9.350/10.013
- dewpoint_depression_c: min/median/max = 3.612/4.468/5.478
- elevation_m: min/median/max = 1243.000/1521.000/1979.000
- monsoon_fraction: min/median/max = 0.777/0.801/0.828
- precipitation_seasonality: min/median/max = 0.658/0.707/0.777
- warmest_month_mean_temperature_c: min/median/max = 18.298/20.749/22.390

近期30年映射保持：14/15。

代表基地（距区内温度中位值最近）：砚山黑鱼洞基地、砚山炭房基地、砚山维摩基地。

- recent_drift_summary dewpoint_depression_c: min/median/max = -0.209/-0.133/0.102
- recent_drift_summary precipitation_mm: min/median/max = -168.161/-20.152/11.101
- recent_drift_summary radiation_mj_m2: min/median/max = -433.252/-412.020/-354.200
- recent_drift_summary temperature_c: min/median/max = 0.265/0.293/0.547
- ytd_2026_same_month_summary dewpoint_depression_c: min/median/max = -0.361/0.002/0.442
- ytd_2026_same_month_summary precipitation_mm: min/median/max = -10.124/83.322/151.557
- ytd_2026_same_month_summary radiation_mj_m2: min/median/max = -79.762/6.629/15.043
- ytd_2026_same_month_summary temperature_c: min/median/max = 0.567/0.646/0.824

### Z5: 温度中位16.4°C / 年降水中位1298mm / 海拔中位1678m

基地数：6；成员：永仁莲池基地、永仁猛虎基地、富民款庄基地、永仁麦拉基地、牟定民乐基地、大理巍山基地。

地理范围：{"latitude": [25.26, 26.08], "longitude": [100.21, 102.67]}。

- annual_mean_temperature_c: min/median/max = 14.528/16.388/19.151
- annual_precipitation_mm: min/median/max = 1121.495/1297.666/1599.810
- annual_radiation_mj_m2: min/median/max = 5962.420/6241.424/6291.991
- annual_temperature_range_c: min/median/max = 10.250/10.866/11.170
- coldest_month_mean_temperature_c: min/median/max = 8.303/9.903/12.453
- dewpoint_depression_c: min/median/max = 5.703/6.860/8.628
- elevation_m: min/median/max = 1573.000/1677.500/1784.000
- monsoon_fraction: min/median/max = 0.827/0.856/0.874
- precipitation_seasonality: min/median/max = 0.749/0.789/0.869
- warmest_month_mean_temperature_c: min/median/max = 18.907/20.722/23.623

近期30年映射保持：4/6。

代表基地（距区内温度中位值最近）：牟定民乐基地、永仁猛虎基地、富民款庄基地。

- recent_drift_summary dewpoint_depression_c: min/median/max = 0.092/0.254/0.287
- recent_drift_summary precipitation_mm: min/median/max = -254.225/-200.924/-184.020
- recent_drift_summary radiation_mj_m2: min/median/max = -419.449/-379.771/-365.207
- recent_drift_summary temperature_c: min/median/max = 0.157/0.475/0.631
- ytd_2026_same_month_summary dewpoint_depression_c: min/median/max = -0.118/-0.007/0.488
- ytd_2026_same_month_summary precipitation_mm: min/median/max = -47.561/2.162/71.257
- ytd_2026_same_month_summary radiation_mj_m2: min/median/max = -55.142/-47.573/-19.078
- ytd_2026_same_month_summary temperature_c: min/median/max = -0.130/0.249/0.557

本报告只提出候选，不建立生产气候区 authority，不开启 S2。BASE_REGISTRY_V1 及 R2 alias authority 保持不变。不使用采摘量、亩产、面积、峰值或预测误差。
