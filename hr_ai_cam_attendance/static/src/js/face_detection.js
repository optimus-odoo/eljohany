/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { jsonrpc } from "@web/core/network/rpc_service";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class FaceDetectionComponent extends Component {
    setup() {
        this.videoElement = null;
        this.overlayCanvas = null;
        this.user = useService('user');
        this.orm = useService("orm")
        this.actionService = useService('action');
        this.dialogService = useService('dialog');
        this.home = useService("home_menu");
        this.notificationService = useService("notification");
        this.rpc = useService('rpc');
        onWillStart(async () => {
        try{
            await this.initializeFaceDetection();
            this.imageData = await this.getUserImageData();
            this.location = await this.getLocation();
            if (this.imageData) {
                const imageUrl = this.convertBase64ToDataUrl(this.imageData); // Convert to Data URL

                // Fetch the image and detect face descriptors
                const image = await faceapi.fetchImage(imageUrl);
                const detections = await faceapi.detectSingleFace(image).withFaceLandmarks().withFaceDescriptor();

                if (detections) {
                    this.detectedFaceDescriptors = detections.descriptor; // Store the profile face descriptor
                }

            }
        } catch (error) {

                console.error("Error during setup:", error);
        }
    });

    }

    getLocation() {
        return new Promise((resolve, reject) => {
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    function (position) {
                        var latitude = position.coords.latitude;
                        var longitude = position.coords.longitude;
                        var loc = "http://www.google.com/maps/place/" + latitude + "," + longitude;
                        console.log('loc', loc);
                        resolve(loc); // Resolve the promise with the location
                    },
                    function (error) {
                        reject("Geolocation error: " + error.message); // Reject if there's an error
                    },
                    { enableHighAccuracy: true } // Request high accuracy
                );
                } else {
                    reject("Geolocation is not supported by this browser.");
                }
        });
    }


    async initializeFaceDetection() {
        // Load face-api.js models from your Odoo module's weights folder
        const modelsPath = '/hr_ai_cam_attendance/static/src/lib/face_api/weights';
        await faceapi.nets.ssdMobilenetv1.loadFromUri(modelsPath); // Face detection model
        await faceapi.nets.faceLandmark68Net.loadFromUri(modelsPath); // Facial landmarks
        await faceapi.nets.faceRecognitionNet.loadFromUri(modelsPath);
        await faceapi.nets.tinyFaceDetector.loadFromUri(modelsPath);

        // Access video and canvas elements
        this.videoElement = document.getElementById("videoElement");
        this.overlayCanvas = document.getElementById("overlayCanvas");
        return true
    }

    async getUserImageData() {
        const data = await this.orm.searchRead('res.users', [['id', '=', this.user.userId]],["image_1920"]);
        return data[0].image_1920
    }

    convertBase64ToDataUrl(base64String) {
        return `data:image/jpeg;base64,${base64String}`;
    }

    startVideoStream() {
        navigator.mediaDevices.getUserMedia({ video: true })
            .then((stream) => {
                document.getElementById("videoElement").srcObject = stream;
            })
            .catch((err) => {
                console.error("Error accessing the camera: ", err);
            });
        document.getElementById("videoElement").style.transform = "scaleX(-1)";
        this.detectFaces();
    }

    async detectFaces() {
        console.log('Starting face detection...');
        const canvas = document.getElementById("overlayCanvas");
        const video = document.getElementById("videoElement");
        let match = false;
        let movementDetected = false;

        const context = canvas.getContext("2d");
        context.setTransform(-1, 0, 0, 1, canvas.width, 0); // يعكس المحتوى أفقياً
        const displaySize = { width: 182, height: 204 };
        faceapi.matchDimensions(canvas, displaySize);
        let intervalId;

        let prevNosePosition = null; // Track the nose position for head movement detection
        let moveDirection = null; // Direction of detected movement: "UP", "DOWN", "LEFT", "RIGHT"

        // Perform face detection at intervals
        intervalId = setInterval(async () => {
            const options = new faceapi.TinyFaceDetectorOptions({ inputSize: 160, scoreThreshold: 0.5 });
            const detections = await faceapi.detectSingleFace(video, options).withFaceLandmarks().withFaceDescriptor();

            if (detections) {
                const resizedDetections = faceapi.resizeResults(detections, displaySize);
                faceapi.draw.drawDetections(canvas, resizedDetections);
                faceapi.draw.drawFaceLandmarks(canvas, resizedDetections);

                // Get nose position for movement detection
                const landmarks = detections.landmarks;
                const nose = landmarks.getNose();
                const nosePosition = { x: nose[3].x, y: nose[3].y }; // Middle of the nose

                if (prevNosePosition) {
                    const dx = nosePosition.x - prevNosePosition.x; // Horizontal movement
                    const dy = nosePosition.y - prevNosePosition.y; // Vertical movement

                    // Detect significant movements
                    if (Math.abs(dx) > 5) moveDirection = dx > 0 ? "RIGHT" : "LEFT";
                    if (Math.abs(dy) > 5) moveDirection = dy > 0 ? "DOWN" : "UP";

                    if (moveDirection) {
                        console.log(`Head moved: ${moveDirection}`);
                        movementDetected = true; // Mark movement as detected
                    }
                }
                prevNosePosition = nosePosition;

                // Check for liveness (blink + movement)
                const leftEye = landmarks.getLeftEye();
                const rightEye = landmarks.getRightEye();
                const leftEAR = this.calculateEAR(leftEye);
                const rightEAR = this.calculateEAR(rightEye);
                const EARThreshold = 0.283;
                console.log('leftEAR',leftEAR);
                console.log('right EAR',rightEAR);

                if (leftEAR > EARThreshold && rightEAR > EARThreshold && movementDetected) {
                    console.log("Liveness confirmed with blink and head movement.");

                    if (this.detectedFaceDescriptors) {
                        const distance = faceapi.euclideanDistance(this.detectedFaceDescriptors, detections.descriptor);
                        if (distance < 0.6 && !match) {
                            match = true;
                            console.log("Faces match!");
                            try {
                                const loc = await this.getLocation();
                                const imageBytes = await this.captureImageBytes(video);
                                const res = await this.rpc('/face_recognition/save_attendance', {
                                    payload: {
                                        'location': loc,
                                        'image_bytes': imageBytes, // Send image bytes
                                    },
                                });
                                if (res) {
                                    clearInterval(intervalId); // Stop the detection interval
                                    setTimeout(() => {
                                        this.closePopup();
                                        this.notificationService.add('Attendance Successfully', { type: 'success' });
                                    }, 300);
                                }
                            } catch (error) {
                                console.error(error);
                            }
                        }
                    }
                }

                // Clear the canvas for the next frame
                context.clearRect(0, 0, canvas.width, canvas.height);
            }
        }, 100);
    }

    async captureImageBytes(videoElement) {
        const canvas = document.createElement("canvas");
        canvas.width = videoElement.videoWidth;
        canvas.height = videoElement.videoHeight;

        const context = canvas.getContext("2d");
        context.drawImage(videoElement, 0, 0, canvas.width, canvas.height);

        // Convert canvas to base64
        const dataUrl = canvas.toDataURL("image/jpeg");
        const base64 = dataUrl.replace(/^data:image\/jpeg;base64,/, ""); // Remove the data URL prefix
        return base64;
    }

    calculateEAR(eye) {
        const A = this.distance(eye[1], eye[5]);
        const B = this.distance(eye[2], eye[4]);
        const C = this.distance(eye[0], eye[3]);
        return (A + B) / (2.0 * C);
    }

    distance(point1, point2) {
        return Math.sqrt(Math.pow(point1.x - point2.x, 2) + Math.pow(point1.y - point2.y, 2));
    }



    closePopup() {
        // Stop video stream
        const videoElement = document.getElementById("videoElement");;
        const stream = videoElement?.srcObject;

        if (stream) {
            const tracks = stream.getTracks();
            tracks.forEach((track) => track.stop()); // Stop all tracks
        }

        videoElement.srcObject = null;
        this.home.toggle(true)

    }
}

FaceDetectionComponent.template = "hr_ai_cam_attendance.FaceDetectionTemplate";
registry.category("actions").add("face_detection", FaceDetectionComponent);