"""Conservative image-geometry candidates, never clinical ankle measurements.

No ML dependency here: this is independently testable post-processing of
COCO-WholeBody keypoints. A named heel-raise task must be confirmed by a human;
these rules do not classify exercise type.
"""
import math
from statistics import median

SIDE_POINTS = {"left": (13, 15, 17, 18, 19), "right": (14, 16, 20, 21, 22)}
SCORE_MIN = 0.45
UP = 0.22
DOWN = 0.08


def point_distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def observation(t, keypoints=None, scores=None, side="left", width=1280,
                height=720, people=1, detector_confidence=1.0):
    """Return a feature observation with explicit rejection reasons."""
    sample = {"t": float(t), "heelLift": None, "confidence": 0.0,
              "valid": False, "reason": "", "people": people}
    if people != 1:
        sample["reason"] = "画面无人" if people == 0 else "画面有多人，无法可靠确认分析对象"
        return sample
    if keypoints is None or scores is None or len(keypoints) != 133 or len(scores) != 133:
        sample["reason"] = "未获得完整人体关键点"
        return sample
    knee_i, ankle_i, toe_i, small_i, heel_i = SIDE_POINTS[side]
    required = [knee_i, ankle_i, toe_i, heel_i]
    if not all(math.isfinite(float(x)) for i in required for x in keypoints[i][:2]):
        sample["reason"] = "关键点坐标异常"
        return sample
    confidence = min(float(scores[i]) for i in required)
    sample["confidence"] = round(max(0.0, min(confidence, 1.0)), 4)
    if not math.isfinite(confidence) or confidence < SCORE_MIN or detector_confidence < 0.5:
        sample["reason"] = "膝、踝、脚跟或脚趾识别置信度不足"
        return sample
    knee, ankle, toe, heel = [keypoints[i] for i in required]
    foot = point_distance(toe, heel)
    tibia = point_distance(knee, ankle)
    if foot < max(18.0, width * 0.012) or tibia < 30:
        sample["reason"] = "足部或小腿在画面中过小"
        return sample
    if not 0.12 <= foot / tibia <= 1.25:
        sample["reason"] = "足部和小腿点位比例异常，需复核遮挡或误识别"
        return sample
    if any(not (3 <= float(keypoints[i][0]) < width - 3 and
                    3 <= float(keypoints[i][1]) < height - 3) for i in required):
        sample["reason"] = "足部或下肢贴近画面边缘"
        return sample
    if abs(toe[0] - heel[0]) / foot < 0.65:
        sample["reason"] = "当前足部投影不适合侧面提踵观察"
        return sample
    if (ankle[1] - knee[1]) / tibia < 0.65:
        sample["reason"] = "小腿方向不符合当前站姿演示条件"
        return sample
    if float(scores[small_i]) >= SCORE_MIN:
        if point_distance(toe, keypoints[small_i]) / foot > 0.60:
            sample["reason"] = "足部视角或脚趾点位异常，需更清楚的侧面画面"
            return sample
    sample.update(valid=True, heelLift=float((toe[1] - heel[1]) / foot),
                  toeX=float(toe[0]), toeY=float(toe[1]), footLength=float(foot))
    return sample


def filter_motion(samples):
    """Reject moving support feet and large scale changes, reset across gaps.

Toe anchoring is a conservative stationary-camera heuristic. It does not prove
ground contact or compensate arbitrary camera motion.
"""
    out, anchor, last_t = [], None, None
    for source in samples:
        s = dict(source)
        if last_t is not None and s["t"] - last_t > .26:
            anchor = None
        last_t = s["t"]
        if not s["valid"]:
            anchor = None
        elif anchor is None:
            anchor = (s["toeX"], s["toeY"], s["footLength"])
        else:
            travel = math.hypot(s["toeX"] - anchor[0], s["toeY"] - anchor[1]) / anchor[2]
            scale = s["footLength"] / anchor[2]
            if travel > .40 or not .70 <= scale <= 1.45:
                s.update(valid=False, heelLift=None,
                         reason="支撑脚位置或画面尺度变化过大，不能可靠计数")
                # Keep the original anchor: walking away cannot repeatedly
                # establish new baselines and fabricate stationary cycles.
        out.append(s)
    return out


def count_cycles(samples):
    """Require a stable near-level starting foot and full up/down candidates."""
    events, calibration, window = [], [], []
    baseline, phase, start, peak, peak_value = None, "down", None, None, None
    high_frames, previous_t, anchored_frames = 0, None, 0
    for s in samples:
        t = s["t"]
        if not s["valid"] or (previous_t is not None and t - previous_t > .26):
            calibration, window = [], []
            baseline, phase, start, peak, peak_value = None, "down", None, None, None
            high_frames = 0
            previous_t = t
            continue
        previous_t = t
        value = float(s["heelLift"])
        if baseline is None:
            calibration.append((t, value))
            calibration = [(tt, v) for tt, v in calibration if t - tt <= .7]
            values = [v for _, v in calibration]
            if (len(values) >= 4 and t - calibration[0][0] >= .35
                    and max(values) - min(values) <= .07 and abs(median(values)) <= .20):
                baseline = median(values)
                anchored_frames += len(values)
            continue
        anchored_frames += 1
        window.append(value)
        window = window[-3:]
        value = median(window) - baseline
        if phase == "down":
            if value > DOWN:
                phase, start, peak, peak_value = "rising", t, t, value
                high_frames = 0
        else:
            if value > peak_value:
                peak, peak_value = t, value
            if value >= UP:
                high_frames += 1
                phase = "high"
            if t - start > 8.0:
                phase, start, peak, peak_value = "down", None, None, None
                high_frames = 0
                continue
            if value <= DOWN:
                if phase == "high" and high_frames >= 2 and .60 <= t - start <= 8:
                    events.append({"start": round(start, 3), "peak": round(peak, 3),
                                   "end": round(t, 3)})
                phase, start, peak, peak_value = "down", None, None, None
                high_frames = 0
    return events, anchored_frames


def summarize(samples, duration, fps, side):
    filtered = filter_motion(samples)
    events, calibrated = count_cycles(filtered)
    valid = sum(s["valid"] for s in filtered)
    coverage = valid / len(filtered) if filtered else 0.0
    multiple = any(s.get("people", 1) > 1 for s in filtered)
    quality = "usable" if coverage >= .8 and calibrated >= 12 and duration >= 2 else "limited"
    if coverage < .4 or not valid:
        quality = "unusable"
    if multiple and quality == "usable":
        quality = "limited"
    can_count = quality == "usable" and not multiple
    warnings = []
    if multiple:
        warnings.append("视频出现多人，候选次数不提供；请人工确认或重新上传单人录像。")
    if coverage < .8:
        warnings.append("有效足部观察覆盖率不足，当前不提供候选次数。")
    if calibrated < 12:
        warnings.append("缺少稳定的初始支撑姿态或连续可用观察，当前不提供候选次数。")
    if duration < 2:
        warnings.append("片段过短，当前不提供候选次数。")
    warnings.append("此模块不识别动作类别，需人工确认录像确为指定侧面提踵任务。")
    warnings.append("图像轨迹和候选次数不是医学踝关节活动度、肌力或康复完成判断。")
    segments, active = [], None
    for s in filtered:
        if not s["valid"]:
            reason = s.get("reason") or "点位不可用"
            if active and active["reason"] == reason:
                active["end"] = round(min(duration, s["t"] + 1 / fps), 3)
            else:
                if active:
                    segments.append(active)
                active = {"start": round(s["t"], 3),
                          "end": round(min(duration, s["t"] + 1 / fps), 3), "reason": reason}
        elif active:
            segments.append(active)
            active = None
    if active:
        segments.append(active)
    accepted = events if can_count else []
    tempos = [e["end"] - e["start"] for e in accepted]
    return {
        "engine": "MMPose RTMPose-M WholeBody + RTMDet-nano",
        "mode": "real_pose", "side": side, "duration": round(duration, 3),
        "fps": fps, "analyzedFrames": len(filtered), "validFrames": valid,
        "coverage": round(coverage, 4), "repCount": len(accepted) if can_count else None,
        "tempoSeconds": round(median(tempos), 3) if tempos else None,
        "quality": quality, "warnings": warnings,
        "series": [{"t": round(s["t"], 3),
                    "heelLift": round(s["heelLift"], 5) if s["valid"] else None,
                    "confidence": s["confidence"], "valid": s["valid"]} for s in filtered],
        "events": accepted, "reviewSegments": segments,
        "overlayVideo": None, "poster": None,
        "notes": ["heelLift = (脚趾图像y − 脚跟图像y) / 当帧脚跟至脚趾像素距离；无物理单位。",
                  "采样视频的连续轨迹经置信度、足部尺寸、视角、支撑点和尺度规则过滤。",
                  "计数需稳定初始姿态与完整抬起—落下周期；不跨遮挡或无效片段补算。",
                  "usable仅表示通过本演示的工程门槛，不表示医学准确或动作标准。",
                  "次数为待人工复核的候选，不自动决定训练阶段。"],
        "modelInfo": {},
    }, filtered
