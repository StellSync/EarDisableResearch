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
import LogoutIcon from "@mui/icons-material/Logout";
import ConsonantsApis from "../../apis/ConsonantsApis";
import CircularProgress from "@mui/material/CircularProgress";

const ConsonantsDialog = ({ open, onClose, quizType }) => {
	const [currentQuestion, setCurrentQuestion] = useState(null);
	const [selectedAnswer, setSelectedAnswer] = useState("");
	const [selectedPayload, setSelectedPayload] = useState(null);
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

	const cleanAudioPath = (path) => {
		return path?.replace("hearing_project_v0.01/", "") ?? "";
	};

	const handleAnswerSelect = (key, label) => {
		// key = 'correct' | 'similar' | 'other'
		setSelectedAnswer(label);
		setSelectedPayload({
			session_id: sessionId,
			user_id: "12345", // add real user ID here
			word_presented: label ?? "",
			chosen_option: key,
			is_verification: questionNumber % 2 === 0, // true for even numbers, false for odd
			consonant_tested:
				currentQuestion?.options?.correct_answer?.changing_consonant ?? "",
			timestamp: new Date().toISOString(),
		});
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
			const response = await ConsonantsApis.submitAnswer(selectedPayload);

			// determine correctness locally (server may also return this)
			const wasCorrect = selectedPayload?.chosen_option === "correct";
			setAnswerCorrect(wasCorrect);
			setShowFeedback(true);

			// keep feedback visible for a short animation duration
			await new Promise((res) => setTimeout(res, 300));
			setIsSubmitting(false);

			if (questionNumber >= 8) {
				handleShowResults();
				return;
			}

			setIsSubmitting(true);
			const nextQuestionResponse = await ConsonantsApis.nextConsonant(
				sessionId
			);
			if (nextQuestionResponse.data) {
				setCurrentQuestion(nextQuestionResponse.data);
				setIsSubmitting(false);
				setQuestionNumber((p) => p + 1);
			} else {
				throw new Error("No question data received");
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
		const resultsResponse = await ConsonantsApis.getResults(sessionId);
		if (resultsResponse && resultsResponse.data) {
			const data = resultsResponse.data;
			// Process and display results
			setResultData(data);

			// New API shape provides `vowels_tested` which is an array of
			// { vowel, correct, incorrect, attempts } objects. Sum the
			// `correct` fields to get the total correct answers.
			let totalCorrect = 0;
			if (Array.isArray(data.consonants_tested)) {
				totalCorrect = data.consonants_tested.reduce((sum, v) => {
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

	const consonantsStartSession = async () => {
		try {
			const payload = {
				user_id: "12345",
			};

			setIsSubmitting(true);
			const response = await ConsonantsApis.startConsonants(payload);

			if (response.data && response.data.session_id) {
				const session = response.data.session_id;
				setSessionId(session);
				const firstQuestionResponse = await ConsonantsApis.nextConsonant(
					session
				);
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
		if (quizType === "consonants" && open) {
			consonantsStartSession();
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
				label: currentQuestion?.options?.correct_answer?.word ?? "",
			},
			{
				key: "similar",
				label: currentQuestion?.options?.similar_answer?.word ?? "",
			},
			{
				key: "other",
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
								{resultData?.consonants_tested.map((v, i) => (
									<Grid item size={6} key={`consonant-result-${i}`}>
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
											{v.consonant}
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
								{resultData?.consonants_tested
									?.filter((v) => Number(v.incorrect) >= 1)
									.map((v, i) => (
										<span key={`vowel-result-${i}`}>
											{v.consonant}
											{i <
											resultData.consonants_tested.filter(
												(v) => Number(v.incorrect) >= 1
											).length -
												1
												? ", "
												: ""}
										</span>
									))}{" "}
								consonants.
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
								src={cleanAudioPath(
									currentQuestion?.options?.correct_answer?.audio_path
								)}
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
											onClick={() => handleAnswerSelect(opt.key, opt.label)}
											sx={{
												py: 2,
												borderRadius: 1,
												fontSize: "1.1rem",
												minWidth: "250px",
												textTransform: "none",
												border:
													selectedAnswer === opt.label
														? "2px solid"
														: "1px solid",
												borderColor:
													selectedAnswer === opt.label
														? "primary.main"
														: "#e0e0e0",
												color:
													selectedAnswer === opt.label
														? "primary.dark"
														: "primary.main",
												minHeight: "60px",
												backgroundColor:
													showFeedback && selectedAnswer === opt.label
														? answerCorrect
															? "rgba(76,175,80,0.08)"
															: "rgba(244,67,54,0.08)"
														: selectedAnswer === opt.label
														? "rgba(25, 118, 210, 0.08)"
														: "transparent",
												transform:
													showFeedback && selectedAnswer === opt.label
														? "scale(1.03)"
														: selectedAnswer === opt.label
														? "scale(1.02)"
														: "none",
												transition:
													"transform .15s ease, background-color .2s ease, border .2s ease",
												boxShadow:
													selectedAnswer === opt.label
														? "0 2px 4px rgba(0,0,0,0.1)"
														: "none",
												"&:hover": {
													backgroundColor:
														selectedAnswer === opt.label
															? "rgba(25, 118, 210, 0.12)"
															: "rgba(0, 0, 0, 0.04)",
													borderColor: "primary.main",
												},
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
								{questionNumber === 8 ? "Finish" : "Next Question"}
							</Button>
						</Grid>
					</Grid>
				)}
			</DialogContent>
		</Dialog>
	);
};

export default ConsonantsDialog;
