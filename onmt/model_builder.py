"""
This file is for models creation, which consults options
and creates each encoder and decoder accordingly.
"""
import os
import re
import torch
import torch.nn as nn
from torch.nn.init import xavier_uniform_
from torchtext.data import RawField

import onmt.modules
from onmt.encoders import str2enc

from onmt.decoders import str2dec
from onmt.inputters.inputter import reload_keyphrase_fields, load_roberta_kp_tokenizer, get_fields

from onmt.modules import Embeddings, CopyGenerator
from onmt.modules.util_class import Cast
from onmt.utils.misc import use_gpu
from onmt.utils.logging import logger
from onmt.utils.parse import ArgumentParser
from onmt.constants import ModelTask
from fairseq.models.bart import BARTModel


def build_embeddings(opt, text_field, for_encoder=True):
    """
    Args:
        opt: the option in current environment.
        text_field(TextMultiField): word and feats field.
        for_encoder(bool): build Embeddings for encoder or decoder?
    """
    emb_dim = opt.src_word_vec_size if for_encoder else opt.tgt_word_vec_size

    pad_indices = [f.vocab.stoi[f.pad_token] for _, f in text_field]
    word_padding_idx, feat_pad_indices = pad_indices[0], pad_indices[1:]

    num_embs = [len(f.vocab) for _, f in text_field]
    num_word_embeddings, num_feat_embeddings = num_embs[0], num_embs[1:]

    freeze_word_vecs_dec = opt.freeze_word_vecs_dec if hasattr(opt, 'freeze_word_vecs_dec') else False
    freeze_word_vecs = freeze_word_vecs_dec if for_encoder else freeze_word_vecs_dec

    emb = Embeddings(
        word_vec_size=emb_dim,
        position_encoding=opt.position_encoding,
        feat_merge=opt.feat_merge,
        feat_vec_exponent=opt.feat_vec_exponent,
        feat_vec_size=opt.feat_vec_size,
        dropout=opt.dropout[0] if type(opt.dropout) is list else opt.dropout,
        word_padding_idx=word_padding_idx,
        feat_padding_idx=feat_pad_indices,
        word_vocab_size=num_word_embeddings,
        feat_vocab_sizes=num_feat_embeddings,
        sparse=(hasattr(opt, 'optim') and opt.optim == "sparseadam"),
        freeze_word_vecs=freeze_word_vecs
    )
    return emb


def build_encoder(opt, embeddings, **kwargs):
    """
    Various encoder dispatcher function.
    Args:
        opt: the option in current environment.
        embeddings (Embeddings): vocab embeddings for this encoder.
    """
    enc_type = opt.encoder_type \
        if opt.model_type == "text" or opt.model_type == "keyphrase" \
        else opt.model_type
    return str2enc[enc_type].from_opt(opt, embeddings, **kwargs)


def build_decoder(opt, embeddings, **kwargs):
    """
    Various decoder dispatcher function.
    Args:
        opt: the option in current environment.
        embeddings (Embeddings): vocab embeddings for this decoder.
    """
    dec_type = "ifrnn" if opt.decoder_type == "rnn" and opt.input_feed \
               else opt.decoder_type
    return str2dec[dec_type].from_opt(opt, embeddings, **kwargs)


def load_test_model(opt, model_path=None):
    if model_path is None:
        model_path = opt.models[0]
        print("Load model path", opt.models[0])
    checkpoint = torch.load(model_path,
                            map_location=lambda storage, loc: storage)

    if hasattr(opt, 'fairseq_model') and opt.fairseq_model:
        # load a Fairseq-trained model, such as BART
        tokenizer = None
        # fairseq models have no previous fields
        fields = get_fields(opt.data_type,
                            n_src_feats=0, n_tgt_feats=0,
                            dynamic_dict=True, # always build src_ex_vocab
                            src_truncate=opt.src_seq_length_trunc,
                            tgt_truncate=opt.tgt_seq_length_trunc,
                            with_align=False)

        if opt.pretrained_tokenizer:
            tokenizer = load_roberta_kp_tokenizer(opt.src_vocab, bpe_dropout=opt.bpe_dropout)
            setattr(opt, 'vocab_size', len(tokenizer))
        else:
            tokenizer = None
        fields = reload_keyphrase_fields(fields, opt, tokenizer=tokenizer)

        # @memray, to make tgt_field be aware of format of targets (multiple phrases)
        setattr(fields["tgt"], 'type', opt.kp_concat_type)
        model_opt = opt
    else:
        # load an ordinary OpenNMT model
        model_opt = ArgumentParser.ckpt_model_opts(checkpoint['opt'])
        ArgumentParser.update_model_opts(model_opt)
        ArgumentParser.validate_model_opts(model_opt)
        fields = checkpoint['vocab']
        src_ex_vocab = RawField()
        fields["src_ex_vocab"] = src_ex_vocab
        if hasattr(model_opt, 'copy_attn'):
            setattr(opt, 'copy_attn', model_opt.copy_attn)

    model = build_base_model(model_opt, fields, use_gpu(opt), checkpoint,
                             opt.gpu)
    if opt.fp32:
        model.float()
    elif opt.int8:
        if opt.gpu >= 0:
            raise ValueError(
                "Dynamic 8-bit quantization is not supported on GPU")
        torch.quantization.quantize_dynamic(model, inplace=True)
    model.eval()
    model.generator.eval()
    return fields, model, model_opt


def build_src_emb(model_opt, fields):
    # Build embeddings.
    if model_opt.model_type == "text" or  model_opt.model_type == "keyphrase":
        src_field = fields["src"]
        src_emb = build_embeddings(model_opt, src_field)
    else:
        src_emb = None
    return src_emb


def build_encoder_with_embeddings(model_opt, fields):
    # Build encoder.
    src_emb = build_src_emb(model_opt, fields)
    encoder = build_encoder(model_opt, src_emb)
    return encoder, src_emb


def build_decoder_with_embeddings(
    model_opt, fields, share_embeddings=False, src_emb=None
):
    # Build embeddings.
    tgt_field = fields["tgt"]
    tgt_emb = build_embeddings(model_opt, tgt_field, for_encoder=False)

    if share_embeddings:
        tgt_emb.word_lut.weight = src_emb.word_lut.weight

    # Build decoder.
    decoder = build_decoder(model_opt, tgt_emb)
    return decoder, tgt_emb


def build_task_specific_model(model_opt, fields):
    # Share the embedding matrix - preprocess with share_vocab required.
    if model_opt.share_embeddings:
        # src/tgt vocab should be the same if `-share_vocab` is specified.
        assert (
            fields["src"].base_field.vocab == fields["tgt"].base_field.vocab
        ), "preprocess with -share_vocab if you use share_embeddings"

    if model_opt.model_task == ModelTask.SEQ2SEQ:
        encoder, src_emb = build_encoder_with_embeddings(model_opt, fields)
        decoder, _ = build_decoder_with_embeddings(
            model_opt,
            fields,
            share_embeddings=model_opt.share_embeddings,
            src_emb=src_emb,
        )
        return onmt.models.NMTModel(encoder=encoder, decoder=decoder)
    elif model_opt.model_task == ModelTask.LANGUAGE_MODEL:
        src_emb = build_src_emb(model_opt, fields)
        decoder, _ = build_decoder_with_embeddings(
            model_opt, fields, share_embeddings=True, src_emb=src_emb
        )
        return onmt.models.LanguageModel(decoder=decoder)
    else:
        raise ValueError(f"No model defined for {model_opt.model_task} task")


def build_base_model(model_opt, fields, gpu, checkpoint=None, gpu_id=None, checkpoint_path=None):
    """Build a model from opts.

    Args:
        model_opt: the option loaded from checkpoint. It's important that
            the opts have been updated and validated. See
            :class:`onmt.utils.parse.ArgumentParser`.
        fields (dict[str, torchtext.data.Field]):
            `Field` objects for the model.
        gpu (bool): whether to use gpu.
        checkpoint: the model gnerated by train phase, or a resumed snapshot
                    model from a stopped training.
        gpu_id (int or NoneType): Which GPU to use.

        @eric-zhizu
        checkpoint_path (str or NoneType): load from checkpoint_path, else load from cache_dir
            for BART model

    Returns:
        the NMTModel.
    """

    if gpu and gpu_id is not None:
        device = torch.device("cuda", gpu_id)
    elif gpu and not gpu_id:
        device = torch.device("cuda")
    elif not gpu:
        device = torch.device("cpu")

    # Build Model
    # OpenNMT models
    if not hasattr(model_opt, 'fairseq_model') or not model_opt.fairseq_model:
        # for back compat when attention_dropout was not defined
        try:
            model_opt.attention_dropout
        except AttributeError:
            model_opt.attention_dropout = model_opt.dropout

        model = build_task_specific_model(model_opt, fields)

        # Build Generator.
        if not model_opt.copy_attn:
            if model_opt.generator_function == "sparsemax":
                gen_func = onmt.modules.sparse_activations.LogSparsemax(dim=-1)
            else:
                gen_func = nn.LogSoftmax(dim=-1)
            generator = nn.Sequential(
                nn.Linear(model_opt.dec_rnn_size,
                          len(fields["tgt"].base_field.vocab)),
                Cast(torch.float32),
                gen_func
            )
            if model_opt.share_decoder_embeddings:
                generator[0].weight = model.decoder.embeddings.word_lut.weight
        else:
            tgt_base_field = fields["tgt"].base_field
            vocab_size = len(tgt_base_field.vocab)
            pad_idx = tgt_base_field.vocab.stoi[tgt_base_field.pad_token]
            generator = CopyGenerator(model_opt.dec_rnn_size, vocab_size, pad_idx)
            if model_opt.share_decoder_embeddings:
                generator.linear.weight = model.decoder.embeddings.word_lut.weight

        # Load the model states from checkpoint or initialize them.
        if checkpoint is not None:
            # This preserves backward-compat for models using customed layernorm
            def fix_key(s):
                s = re.sub(r'(.*)\.layer_norm((_\d+)?)\.b_2',
                           r'\1.layer_norm\2.bias', s)
                s = re.sub(r'(.*)\.layer_norm((_\d+)?)\.a_2',
                           r'\1.layer_norm\2.weight', s)
                return s

            checkpoint['model'] = {fix_key(k): v
                                   for k, v in checkpoint['model'].items()}
            # end of patch for backward compatibility

            model.load_state_dict(checkpoint['model'], strict=False)
            generator.load_state_dict(checkpoint['generator'], strict=False)
        else:
            if model_opt.param_init != 0.0:
                for p in model.parameters():
                    p.data.uniform_(-model_opt.param_init, model_opt.param_init)
                for p in generator.parameters():
                    p.data.uniform_(-model_opt.param_init, model_opt.param_init)
            if model_opt.param_init_glorot:
                for p in model.parameters():
                    if p.dim() > 1:
                        xavier_uniform_(p)
                for p in generator.parameters():
                    if p.dim() > 1:
                        xavier_uniform_(p)

        if hasattr(model, "encoder") and hasattr(model.encoder, "embeddings"):
            model.encoder.embeddings.load_pretrained_vectors(
                model_opt.pre_word_vecs_enc)
        if hasattr(model.decoder, 'embeddings'):
            model.decoder.embeddings.load_pretrained_vectors(
                model_opt.pre_word_vecs_dec)

    # FairSeq models
    else:
        # Build encoder.
        if checkpoint_path:
            bart_dir = os.path.dirname(checkpoint_path)
            checkpoint_file = os.path.basename(checkpoint_path)
            bart_path = os.path.join(bart_dir, checkpoint_file)
            assert os.path.exists(bart_path), 'BART checkpoint is not found! %s ' % bart_path
        else:
            bart_dir = os.path.join(model_opt.cache_dir, 'bart.large.cnn')
            checkpoint_file = 'model.pt'
            bart_path = os.path.join(bart_dir, checkpoint_file)
            assert os.path.exists(bart_path), 'BART checkpoint is not found! %s ' % bart_path

        bart_model = BARTModel.from_pretrained(bart_dir, checkpoint_file=checkpoint_file)
        encoder = build_encoder(model_opt, embeddings=None, bart_model=bart_model, prev_checkpoint=checkpoint)

        # Build decoder.
        decoder = build_decoder(model_opt, embeddings=None, bart_model=bart_model, prev_checkpoint=checkpoint)

        # Build NMTModel(= encoder + decoder).
        model = onmt.models.NMTModel(encoder=encoder, decoder=decoder)

        # Build Generator.
        gen_func = nn.LogSoftmax(dim=-1)
        generator = nn.Sequential(
            nn.Linear(model.decoder.model.output_projection.in_features,
                      model.decoder.model.output_projection.out_features,
                      bias=False),
            Cast(torch.float32),
            gen_func
        )
        generator[0].weight = model.decoder.model.output_projection.weight

    model.generator = generator
    model.to(device)
    # if model_opt.model_dtype == 'fp16' and (hasattr(model_opt, 'optim') and model_opt.optim == 'fusedadam'):
    if model_opt.model_dtype == 'fp16':
        model.half()
    return model


def build_model(model_opt, opt, fields, checkpoint):
    logger.info('Building model...')
    model = build_base_model(model_opt, fields, use_gpu(opt), checkpoint)
    logger.info(model)
    return model
