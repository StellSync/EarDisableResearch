"use client";
import React, { useState, useRef, useEffect } from "react";
import {
	Dialog,
	DialogContent,
	Typography,
	Button,
	Grid,
	DialogTitle,
} from "@mui/material";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import LogoutIcon from "@mui/icons-material/Logout";
import apiDefinitions from "../../apis/apiDefinitions";
import CircularProgress from "@mui/material/CircularProgress";

const QuizDialog = ({ open, onClose, quizType }) => {
	const questions = [
		{
			id: 1,
			question: "ඔයාට කොහොම ද?",
			audioUrl: "/audio/sound1.mp3",
			options: ["Bell", "Horn", "Whistle", "Bird"],
			correctAnswer: "Bell",
		},
		{
			id: 2,
			question: "Identify this musical instrument",
			audioUrl: "/audio/sound2.mp3",
			options: ["Piano", "Guitar", "Drums", "Violin"],
			correctAnswer: "Piano",
		},
	];

	const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
	const [currentQuestion, setCurrentQuestion] = useState(null);
	const [selectedAnswer, setSelectedAnswer] = useState("");
	const [selectedPayload, setSelectedPayload] = useState(null);
	const [score, setScore] = useState(0);
	const [questionNumber, setQuestionNumber] = useState(1);
	const [showResults, setShowResults] = useState(false);
	const [shuffledOptions, setShuffledOptions] = useState([]);
	const [showFeedback, setShowFeedback] = useState(false);
	const [answerCorrect, setAnswerCorrect] = useState(false);
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [resultData, setResultData] = useState(null);
	const [correctAnswersCount, setCorrectAnswersCount] = useState(0);
	const audioRef = useRef(null);
	const [sessionId, setSessionId] = useState(null);

	const handleAnswerSelect = (key, id, label) => {
		// key = 'correct' | 'similar' | 'other'
		setSelectedAnswer(label);
		setSelectedPayload({ selected_key: key, selected_id: id });
	};

	const handlePlayAudio = () => {
		if (audioRef.current) {
			audioRef.current.play();
		}
	};

	const handleSubmit = async () => {
		if (!sessionId || !selectedPayload || isSubmitting) return;

		setIsSubmitting(true);
		try {
			// submit answer
			const response = await apiDefinitions.submitAnswer(
				sessionId,
				selectedPayload
			);

			// determine correctness locally (server may also return this)
			const wasCorrect = selectedPayload?.selected_key === "correct";
			setAnswerCorrect(wasCorrect);
			setShowFeedback(true);

			// keep feedback visible for a short animation duration
			await new Promise((res) => setTimeout(res, 300));
			setIsSubmitting(false);

			if (questionNumber >= 8) {
				handleShowResults();
				return;
			}

			// if API returned next question directly, use it; otherwise request nextVowel
			if (response && response.data) {
				// empty object or null indicates no more questions
				const next = response.data;
				if (
					!next ||
					(Object.keys(next).length === 0 && next.constructor === Object)
				) {
					handleShowResults();
				} else {
					setCurrentQuestion(next);
					setQuestionNumber((p) => p + 1);
				}
			} else {
				// fallback: ask server for next question
				const nextResp = await apiDefinitions.nextVowel(sessionId);
				if (nextResp && nextResp.data) {
					setCurrentQuestion(nextResp.data);
					setQuestionNumber((p) => p + 1);
				} else {
					handleShowResults();
				}
			}
		} catch (error) {
			console.error("Error submitting answer:", error);
		} finally {
			// reset selection and feedback after animation
			setShowFeedback(false);
			setSelectedAnswer("");
			setSelectedPayload(null);
			setIsSubmitting(false);
		}
	};

	const handleClose = () => {
		onClose();
		setQuestionNumber(1);
		setShowResults(false);
		setCurrentQuestion(null);
	};

	const handleShowResults = async () => {
		setShowResults(true);

		// Fetch results from the API
		const resultsResponse = await apiDefinitions.getResults(sessionId);
		if (resultsResponse && resultsResponse.data) {
			const data = resultsResponse.data;
			// Process and display results
			setResultData(data);

			// New API shape provides `vowels_tested` which is an array of
			// { vowel, correct, incorrect, attempts } objects. Sum the
			// `correct` fields to get the total correct answers.
			let totalCorrect = 0;
			if (Array.isArray(data.vowels_tested)) {
				totalCorrect = data.vowels_tested.reduce((sum, v) => {
					// v.correct may be numeric or string; coerce to Number safely
					const c = Number(v.correct) || 0;
					return sum + c;
				}, 0);
			} else if (Array.isArray(data.mapped_answers)) {
				// Backwards-compatible fallback to older mapped_answers shape
				totalCorrect = data.mapped_answers.filter(
					(ans) => ans.is_correct
				).length;
			}

			setCorrectAnswersCount(totalCorrect);
		}
	};

	const vowelStartSession = async () => {
		try {
			const payload = {
				user_id: "12345",
			}; // Add any necessary payload data here

			setIsSubmitting(true);
			const response = await apiDefinitions.startVowels(payload);

			if (response.data && response.data.session_id) {
				const session = response.data.session_id;
				setSessionId(session);
				const firstQuestionResponse = await apiDefinitions.nextVowel(session);
				if (firstQuestionResponse.data) {
					setCurrentQuestion(firstQuestionResponse.data);
					setIsSubmitting(false);
				} else {
					throw new Error("No question data received");
				}
			} else {
				throw new Error("No session ID received from server");
			}
		} catch (error) {
			console.error("Error starting vowel session:", error);
		}
	};

	useEffect(() => {
		if (quizType === "vowels" && open) {
			vowelStartSession();
		}
	}, [quizType, open]);

	// Build and shuffle options (randomize correct and similar positions)
	useEffect(() => {
		if (!currentQuestion) {
			setShuffledOptions([]);
			return;
		}

		const options = [
			{
				key: "correct",
				id: currentQuestion?.correct?.id ?? null,
				label: currentQuestion?.correct?.sinhala_word ?? "",
			},
			{
				key: "similar",
				id: currentQuestion?.similar?.id ?? null,
				label: currentQuestion?.similar?.sinhala_word ?? "",
			},
			{
				key: "other",
				id: null,
				label: "Other",
			},
		];

		// Randomize correct/similar order
		if (Math.random() < 0.5) {
			[options[0], options[1]] = [options[1], options[0]];
		}

		setShuffledOptions(options);
	}, [currentQuestion]);

	return (
		<Dialog
			open={open}
			onClose={(event, reason) => {
				// Prevent closing on backdrop click or Escape key.
				if (reason === "backdropClick" || reason === "escapeKeyDown") return;
				handleClose();
			}}
			disableEscapeKeyDown
			maxWidth="sm"
			fullWidth
		>
			<DialogTitle>{showResults ? "Quiz Results" : "Hearing Quiz"}</DialogTitle>
			<DialogContent>
				{showResults ? (
					<Grid container spacing={2}>
						<Grid item size={12}>
							<Typography variant="h4" align="center" gutterBottom>
								Your Results
							</Typography>
							<Typography
								variant="h2"
								align="center"
								color="primary"
								gutterBottom
							>
								{correctAnswersCount} / {resultData?.total_words_tested}
							</Typography>
							<Grid container spacing={1} sx={{ mb: 1 }}>
								{resultData?.vowels_tested.map((v, i) => (
									<Grid item size={6} key={`vowel-result-${i}`}>
										<Typography
											variant="h5"
											align="center"
											color={
												v.correct > 1
													? "success"
													: v.correct > 1
													? "warning"
													: "error"
											}
										>
											{v.vowel}
										</Typography>
										<Typography
											variant="body1"
											align="center"
											color="text.secondary"
										>
											{v.correct} / {v.attempts}
										</Typography>
									</Grid>
								))}
							</Grid>
							<Typography variant="body1" align="center" gutterBottom>
								You have Trouble Hearing{" "}
								{resultData?.vowels_tested
									?.filter((v) => Number(v.incorrect) >= 1)
									.map((v, i) => (
										<span key={`vowel-result-${i}`}>
											{v.vowel}
											{i <
											resultData.vowels_tested.filter(
												(v) => Number(v.incorrect) >= 1
											).length -
												1
												? ", "
												: ""}
										</span>
									))}{" "}
								vowels.
							</Typography>
							<Grid container justifyContent="center" sx={{ mt: 3 }}>
								<Button
									variant="contained"
									startIcon={<LogoutIcon />}
									onClick={handleClose}
								>
									Exit
								</Button>
							</Grid>
						</Grid>
					</Grid>
				) : isSubmitting ? (
					<Grid container justifyContent="center" sx={{ minHeight: "200px" }}>
						<Grid item size={12} sx={{ textAlign: "center", mt: 4 }}>
							<CircularProgress />
						</Grid>
						<Grid item size={12} sx={{ textAlign: "center" }}>
							<Typography variant="body1">Loading Next Question...</Typography>
						</Grid>
					</Grid>
				) : (
					<Grid container sx={{ px: 3 }}>
						<Grid item xs={12} sx={{ textAlign: "center" }}>
							<Typography variant="body2" sx={{ mb: 2 }}>
								Question: {questionNumber}
							</Typography>
						</Grid>

						<Grid item size={12} sx={{ mb: 3 }}>
							<Button
								variant="contained"
								color="success"
								startIcon={<PlayArrowIcon />}
								onClick={handlePlayAudio}
								sx={{
									borderRadius: 1,
									fontSize: "1rem",
									boxShadow: 3,
									mb: 4,
								}}
							>
								Play Audio
							</Button>
							<audio
								ref={audioRef}
								src={currentQuestion?.correct?.audio_path}
							/>
						</Grid>

						<Grid item xs={12} sx={{ mb: 3 }}>
							<Grid
								container
								spacing={2}
								justifyContent="center"
								sx={{ maxWidth: "800px", mx: "auto" }}
							>
								{shuffledOptions.map((opt, idx) => (
									<Grid item size={6} key={`${opt.key}-${idx}`}>
										<Button
											fullWidth
											variant="outlined"
											onClick={() =>
												handleAnswerSelect(opt.key, opt.id, opt.label)
											}
											sx={{
												py: 2,
												borderRadius: 1,
												fontSize: "1.1rem",
												minWidth: "250px",
												textTransform: "none",
												borderColor:
													selectedAnswer === opt.label
														? "primary.main"
														: "#e0e0e0",
												color: "primary.main",
												minHeight: "60px",
												backgroundColor:
													showFeedback && selectedAnswer === opt.label
														? answerCorrect
															? "rgba(76,175,80,0.08)"
															: "rgba(244,67,54,0.08)"
														: "transparent",
												transform:
													showFeedback && selectedAnswer === opt.label
														? "scale(1.03)"
														: "none",
												transition:
													"transform .15s ease, background-color .2s ease",
											}}
										>
											{opt.label}
										</Button>
									</Grid>
								))}
							</Grid>
						</Grid>

						<Grid
							item
							size={6}
							sx={{ display: "flex", justifyContent: "flex-start" }}
						>
							<Button
								variant="contained"
								onClick={handleShowResults}
								color="error"
								sx={{
									py: 1.5,
									px: 4,
									borderRadius: 1,
									fontSize: "0.9rem",
								}}
							>
								End Session
							</Button>
						</Grid>
						<Grid
							item
							size={6}
							sx={{ display: "flex", justifyContent: "flex-end" }}
						>
							<Button
								variant="contained"
								onClick={handleSubmit}
								disabled={!selectedAnswer || isSubmitting}
								sx={{
									py: 1.5,
									px: 4,
									borderRadius: 1,
									fontSize: "0.9rem",
									opacity: !selectedAnswer ? 0.7 : 1,
									bgcolor: !selectedAnswer ? "#e0e0e0" : "primary.main",
								}}
							>
								{currentQuestionIndex === questions.length - 1
									? "Finish"
									: "Next Question"}
							</Button>
						</Grid>
					</Grid>
				)}
			</DialogContent>
		</Dialog>
	);
};

export default QuizDialog;
