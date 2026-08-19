<div align="center">

# AV Autoencoder & Pose2OSC for GestureCap

**GSoC 2026 Final Submission Report**  
Mathew Vallejo

[Final Report PDF](Pose2OSC_GestureCap_Final%20Report.pdf)

</div>

---

## Overview

This work was developed for the GestureCap project hosted by INCF for the 2026
Google Summer of Code (GSoC) session. GestureCap is dedicated to exploring the
use of real-time gesture data for control of digital sound parameters. Previous
work has consisted of establishing a pipeline for using the MediaPipe hand
tracking software, developing low-latency test protocols for real-time
performance, and developing OSC-based interfaces between Python and visual
programming languages such as Pure Data and Max/MSP.

The established goal for this GSoC contribution was to design and build a
digital "Hypertheremin" that allows performers to control a digitally modelled
theremin synthesizer via video input using the same, or similar, physical
gestures used to control a traditional analog theremin instrument.

This contribution focuses on the video input stage of the digital instrument.
Hand tracking data obtained via MediaPipe is used for initial hand recognition
and passed through the gesture recognition pipeline, culminating in a mapping of
gesture data to specific instrument controls. Gesture data is sent between the
video input stage and the synthesizer engine via the Open Sound Control (OSC)
protocol.

## Project Components

| Component | Role | Runtime Output |
| --- | --- | --- |
| [AV Autoencoder](AV_Autoencoder/) | Learns gesture structure from recorded theremin performances using calibrated MediaPipe hand-landmark data and aligned audio features. | Cluster, confidence, motion energy, selected landmarks, and latent-vector data over OSC. |
| [Pose2OSC](Pose2OSC/) | Provides a practical performer-driven gesture enrollment application for live OSC control without neural-network training. | Gesture state, triggers, confidence values, and continuous landmark OSC messages. |

## AV Autoencoder

The AV Autoencoder pipeline was developed to learn gesture structure from
recorded theremin performances using calibrated MediaPipe hand-landmark data and
aligned audio features. The system is organized into three Python stages:

| Stage | Folder | Purpose |
| --- | --- | --- |
| Camera Calibration and Preprocessing | [AV_Autoencoder/av_Camera_Calibration_Preprocess](AV_Autoencoder/av_Camera_Calibration_Preprocess/) | Calibrates cameras, undistorts frames, runs MediaPipe hand tracking, and writes landmark CSVs. |
| Gated Recurrent Unit Autoencoder Training | [AV_Autoencoder/av_GRU_autoencoder](AV_Autoencoder/av_GRU_autoencoder/) | Builds fixed-length motion windows, trains the GRU autoencoder, embeds windows, clusters latent vectors, evaluates clusters, and exports runtime artifacts. |
| Gesture OSC Runtime | [AV_Autoencoder/av_Gesture_OSC_runtime](AV_Autoencoder/av_Gesture_OSC_runtime/) | Runs live camera or replay video input through the trained encoder and sends model outputs over OSC. |

In training, fixed-length motion windows are encoded into a latent gesture space
while audio-derived log-mel features act as an auxiliary target, helping the
model organize movement patterns around audiovisual performance structure.
After training, the latent embeddings are clustered and exported as a runtime
package.

The live runtime uses motion landmarks only, assigns incoming gesture windows to
learned clusters, and sends cluster, confidence, motion-energy, landmark, and
latent-vector data over OSC for mapping to the Hypertheremin synthesizer.

## Pose2OSC

[Pose2OSC](Pose2OSC/) was developed as a practical alternative to the
autoencoder approach. It is a desktop application for performer-driven gesture
enrollment and live OSC control.

Users record examples of desired hand poses into a JSON gesture manifest. The
runtime then extracts normalized MediaPipe hand-shape features and performs
lightweight KNN recognition without requiring neural-network training. This
provides a low-latency, explicit control path for the Hypertheremin synthesizer
while preserving continuous landmark OSC output for expressive mapping in
Max/MSP.

## Current State

Each component has working end-to-end functionality, beginning with gesture
input and ending in OSC output with dedicated test patches for prototyping.

| Area | Current Capability |
| --- | --- |
| AV Autoencoder | Processes recorded training data, builds motion/audio windows, trains the GRU autoencoder, clusters latent embeddings, exports a runtime model package, and sends runtime OSC output. |
| Pose2OSC | Captures user gestures, stores performer manifests, recognizes enrolled poses live, and sends gesture and landmark data over OSC. |
| OSC Integration | Includes output-message documentation and example routing material for Max/MSP prototyping. |

The OSC output stage was developed in conjunction with a co-contributor
responsible for building the audio synthesizer. The project includes a complete
list of output messages and an example patch for OSC routing in Max/MSP.

## Code Contributions

The code contributions consist of individual Python project folders for the
three stages of the AV Autoencoder and a fourth folder containing the Pose2OSC
code and application launcher.

| Folder | Description |
| --- | --- |
| [AV_Autoencoder/av_Camera_Calibration_Preprocess](AV_Autoencoder/av_Camera_Calibration_Preprocess/) | Camera calibration, undistortion, MediaPipe extraction, and CSV feature output. |
| [AV_Autoencoder/av_GRU_autoencoder](AV_Autoencoder/av_GRU_autoencoder/) | Window building, GRU training, embedding, clustering, evaluation, plotting, and runtime export. |
| [AV_Autoencoder/av_Gesture_OSC_runtime](AV_Autoencoder/av_Gesture_OSC_runtime/) | Live and replay runtime for model inference, smoothing, calibration compatibility, and OSC output. |
| [Pose2OSC](Pose2OSC/) | Desktop app, command-line runtime, gesture manifests, KNN recognizer, OSC sender, launcher, and tests. |

Each folder contains its own `README.md` with a walkthrough for setting up the
code environment, running the scripts, and understanding dataflow between
project stages.

## Remaining Work

The area of this work that would benefit most from targeted experiments and
investigation is the collection and cleaning of video training data for the AV
Autoencoder. It would be helpful to know how a model trained on data from one
performer translates to use by another performer.

This endeavor is in pursuit of a Hypertheremin that learns its performer, or at
least common performance characteristics, as opposed to a performer needing to
learn the new instrument.

For Pose2OSC, more experimentation with accomplished analog theremin players
would provide insight into how the gesture manifest might best be captured to
support an organic approach to the Hypertheremin from a playability standpoint.
This involves decisions surrounding how many gestures to capture for complete
control, and how those gestures should be mapped to the synthesizer engine.

## Challenges / Lessons

This project involved unraveling a web of design decisions around gesture
capture, machine learning, real-time control, and musical performance. The work
made it possible to pursue multiple approaches to solving the same problem,
determine what works best under given circumstances, and ensure that all sides
of the system can functionally integrate with each other.

Integration between video/gesture input and the Hypertheremin synthesizer was a
particularly satisfying problem to solve, as it was effectively the culmination
of the work. The most challenging aspect of the project came from the AV
Autoencoder design, which ultimately required being broken down into several
stages to ensure clear data transfer between calibration, training, runtime
export, and OSC output.
