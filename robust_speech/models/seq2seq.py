"""A sequence-to-sequence ASR system with librispeech supporting adversarial attacks.
The system employs an encoder, a decoder, and an attention mechanism
between them. Decoding is performed with beamsearch coupled with a neural
language model.

Inspired from SpeechBrain Seq2Seq 
(https://github.com/speechbrain/speechbrain/blob/develop/recipes/LibriSpeech/ASR/seq2seq/train.py)
"""
import speechbrain as sb
import torch

import sys
sys.path.append('/root/class/cmu/DL/project/robust_speech')
import robust_speech as rs
from robust_speech.adversarial.brain import AdvASRBrain, AugMaxASRBrain
from robust_speech.adversarial.attacks.augmax import AugMixModule

# Define training procedure


class S2SASR(AdvASRBrain):
    """
    Encoder-decoder models using RNNs
    """

    def compute_forward(self, batch, stage):
        """Forward computations from the waveform batches to the output probabilities."""
        self.modules.normalize.to(self.device)
        wavs, wav_lens = batch.sig
        if not stage == rs.Stage.ATTACK:
            batch = batch.to(self.device)
            wavs, wav_lens = wavs.to(self.device), wav_lens.to(self.device)
        tokens_bos, _ = batch.tokens_bos
        # wavs, wav_lens = wavs.to(self.device), wav_lens.to(self.device)
        # Add augmentation if specified
        if stage == sb.Stage.TRAIN:
            if hasattr(self.modules, "env_corrupt"):
                wavs_noise = self.modules.env_corrupt(wavs, wav_lens)
                wavs = torch.cat([wavs, wavs_noise], dim=0)
                wav_lens = torch.cat([wav_lens, wav_lens])
                tokens_bos = torch.cat([tokens_bos, tokens_bos], dim=0)

            if hasattr(self.hparams, "augmentation"):
                wavs = self.hparams.augmentation(wavs, wav_lens)
        # Forward pass
        feats = self.hparams.compute_features(wavs)
        if stage == sb.Stage.TRAIN:
            feats = self.modules.normalize(feats, wav_lens)
        else:
            # don't update normalization outside of training!
            feats = self.modules.normalize(
                feats, wav_lens, epoch=self.modules.normalize.update_until_epoch + 1
            )
        if stage == rs.Stage.ATTACK:
            encoded = self.modules.enc(feats)
        else:
            encoded = self.modules.enc(feats.detach())
        e_in = self.modules.emb(tokens_bos)  # y_in bos + tokens
        hidden, _ = self.modules.dec(e_in, encoded, wav_lens)
        # Output layer for seq2seq log-probabilities
        logits = self.modules.seq_lin(hidden)
        p_seq = self.hparams.log_softmax(logits)

        # Compute outputs
        if stage == sb.Stage.TRAIN or stage == rs.Stage.ATTACK:
            current_epoch = self.hparams.epoch_counter.current
            if current_epoch <= self.hparams.number_of_ctc_epochs:
                # Output layer for ctc log-probabilities
                logits = self.modules.ctc_lin(encoded)
                p_ctc = self.hparams.log_softmax(logits)
                return p_ctc, p_seq, wav_lens
            else:
                return p_seq, wav_lens
        else:
            if stage == sb.Stage.VALID:
                p_tokens, _ = self.hparams.valid_search(encoded, wav_lens)
            else:
                p_tokens, _ = self.hparams.test_search(encoded, wav_lens)
            return p_seq, wav_lens, p_tokens

    def compute_objectives(
        self, predictions, batch, stage, adv=False, targeted=False, reduction="mean"
    ):
        """Computes the loss (CTC+NLL) given predictions and targets."""

        current_epoch = self.hparams.epoch_counter.current
        if stage == sb.Stage.TRAIN or stage == rs.Stage.ATTACK:
            if current_epoch <= self.hparams.number_of_ctc_epochs:
                p_ctc, p_seq, wav_lens = predictions
            else:
                p_seq, wav_lens = predictions
        else:
            p_seq, wav_lens, predicted_tokens = predictions

        ids = batch.id
        tokens_eos, tokens_eos_lens = batch.tokens_eos
        tokens, tokens_lens = batch.tokens

        if hasattr(self.modules, "env_corrupt") and stage == sb.Stage.TRAIN:
            tokens_eos = torch.cat([tokens_eos, tokens_eos], dim=0)
            tokens_eos_lens = torch.cat([tokens_eos_lens, tokens_eos_lens], dim=0)
            tokens = torch.cat([tokens, tokens], dim=0)
            tokens_lens = torch.cat([tokens_lens, tokens_lens], dim=0)

        loss_seq = self.hparams.seq_cost(
            p_seq, tokens_eos, length=tokens_eos_lens, reduction=reduction
        )

        # Add ctc loss if necessary
        if (
            stage == sb.Stage.TRAIN or stage == rs.Stage.ATTACK
        ) and current_epoch <= self.hparams.number_of_ctc_epochs:
            loss_ctc = self.hparams.ctc_cost(
                p_ctc, tokens, wav_lens, tokens_lens, reduction=reduction
            )
            loss = self.hparams.ctc_weight * loss_ctc
            loss += (1 - self.hparams.ctc_weight) * loss_seq
        else:
            loss = loss_seq

        if stage != sb.Stage.TRAIN and stage != rs.Stage.ATTACK:
            # Decode token terms to words
            predicted_words = [
                self.tokenizer.decode_ids(utt_seq).split(" ")
                for utt_seq in predicted_tokens
            ]
            target_words = [wrd.split(" ") for wrd in batch.wrd]
            if adv:
                if targeted:
                    self.adv_wer_metric_target.append(
                        ids, predicted_words, target_words
                    )
                    self.adv_cer_metric_target.append(
                        ids, predicted_words, target_words
                    )
                else:
                    self.adv_wer_metric.append(ids, predicted_words, target_words)
                    self.adv_cer_metric.append(ids, predicted_words, target_words)
            else:
                self.wer_metric.append(ids, predicted_words, target_words)
                self.cer_metric.append(ids, predicted_words, target_words)

        return loss


class S2SAugMaxASR(AugMaxASRBrain):
    """
    Encoder-decoder models using RNNs
    """
    def __init__(
        self,
        modules=None,
        opt_class=None,
        hparams=None,
        run_opts=None,
        checkpointer=None,
        attacker=None,
    ):
        AugMaxASRBrain.__init__(
            self,
            modules=modules,
            opt_class=opt_class,
            hparams=hparams,
            run_opts=run_opts,
            checkpointer=checkpointer,
            attacker=attacker,
        )
        self.augmix_model = AugMixModule(mixture_width=3, device=self.device)


    def compute_forward(self, batch, stage, augmix=False):
        """Forward computations from the waveform batches to the output probabilities."""
        self.modules.normalize.to(self.device)
        wavs, wav_lens = batch.sig
        if not stage == rs.Stage.ATTACK:
            batch = batch.to(self.device)
            wavs, wav_lens = wavs.to(self.device), wav_lens.to(self.device)
        if augmix:
            wavs = self.augmix_model(wavs)
        tokens_bos, _ = batch.tokens_bos
        # wavs, wav_lens = wavs.to(self.device), wav_lens.to(self.device)
        # Add augmentation if specified
        # if stage == sb.Stage.TRAIN:
            # if hasattr(self.modules, "env_corrupt"):
            #     wavs_noise = self.modules.env_corrupt(wavs, wav_lens)
            #     wavs = torch.cat([wavs, wavs_noise], dim=0)
            #     wav_lens = torch.cat([wav_lens, wav_lens])
            #     tokens_bos = torch.cat([tokens_bos, tokens_bos], dim=0)

        #     if hasattr(self.hparams, "augmentation"):
        #         wavs = self.hparams.augmentation(wavs, wav_lens)
        # Forward pass
        feats = self.hparams.compute_features(wavs)
        if stage == sb.Stage.TRAIN:
            feats = self.modules.normalize(feats, wav_lens)
        else:
            # don't update normalization outside of training!
            feats = self.modules.normalize(
                feats, wav_lens, epoch=self.modules.normalize.update_until_epoch + 1
            )
        if stage == rs.Stage.ATTACK:
            encoded = self.modules.enc(feats)
        else:
            encoded = self.modules.enc(feats.detach())
        e_in = self.modules.emb(tokens_bos)  # y_in bos + tokens
        hidden, _ = self.modules.dec(e_in, encoded, wav_lens)
        # Output layer for seq2seq log-probabilities
        logits = self.modules.seq_lin(hidden)
        p_seq = self.hparams.log_softmax(logits)

        # Compute outputs
        if stage == sb.Stage.TRAIN or stage == rs.Stage.ATTACK:
            current_epoch = self.hparams.epoch_counter.current
            if current_epoch <= self.hparams.number_of_ctc_epochs:
                # Output layer for ctc log-probabilities
                logits = self.modules.ctc_lin(encoded)
                p_ctc = self.hparams.log_softmax(logits)
                return p_ctc, p_seq, wav_lens
            else:
                return p_seq, wav_lens
        else:
            if stage == sb.Stage.VALID:
                p_tokens, _ = self.hparams.valid_search(encoded, wav_lens)
            else:
                p_tokens, _ = self.hparams.test_search(encoded, wav_lens)
            return p_seq, wav_lens, p_tokens

    def compute_objectives(
        self, predictions, batch, stage, adv=False, targeted=False, reduction="mean"
    ):
        """Computes the loss (CTC+NLL) given predictions and targets."""

        current_epoch = self.hparams.epoch_counter.current
        if stage == sb.Stage.TRAIN or stage == rs.Stage.ATTACK:
            if current_epoch <= self.hparams.number_of_ctc_epochs:
                p_ctc, p_seq, wav_lens = predictions
            else:
                p_seq, wav_lens = predictions
        else:
            p_seq, wav_lens, predicted_tokens = predictions

        ids = batch.id
        tokens_eos, tokens_eos_lens = batch.tokens_eos
        tokens, tokens_lens = batch.tokens

        if hasattr(self.modules, "env_corrupt") and stage == sb.Stage.TRAIN:
            tokens_eos = torch.cat([tokens_eos, tokens_eos], dim=0)
            tokens_eos_lens = torch.cat([tokens_eos_lens, tokens_eos_lens], dim=0)
            tokens = torch.cat([tokens, tokens], dim=0)
            tokens_lens = torch.cat([tokens_lens, tokens_lens], dim=0)

        loss_seq = self.hparams.seq_cost(
            p_seq, tokens_eos, length=tokens_eos_lens, reduction=reduction
        )

        # Add ctc loss if necessary
        if (
            stage == sb.Stage.TRAIN or stage == rs.Stage.ATTACK
        ) and current_epoch <= self.hparams.number_of_ctc_epochs:
            loss_ctc = self.hparams.ctc_cost(
                p_ctc, tokens, wav_lens, tokens_lens, reduction=reduction
            )
            loss = self.hparams.ctc_weight * loss_ctc
            loss += (1 - self.hparams.ctc_weight) * loss_seq
        else:
            loss = loss_seq

        if stage != sb.Stage.TRAIN and stage != rs.Stage.ATTACK:
            # Decode token terms to words
            predicted_words = [
                self.tokenizer.decode_ids(utt_seq).split(" ")
                for utt_seq in predicted_tokens
            ]
            target_words = [wrd.split(" ") for wrd in batch.wrd]
            if adv:
                if targeted:
                    self.adv_wer_metric_target.append(
                        ids, predicted_words, target_words
                    )
                    self.adv_cer_metric_target.append(
                        ids, predicted_words, target_words
                    )
                else:
                    self.adv_wer_metric.append(ids, predicted_words, target_words)
                    self.adv_cer_metric.append(ids, predicted_words, target_words)
            else:
                self.wer_metric.append(ids, predicted_words, target_words)
                self.cer_metric.append(ids, predicted_words, target_words)

        return loss
