# -*- coding: utf-8 -*-

import sys

sys.path.append('.')

from src import *
from src.eval import *
from src.model.template import *
from src.module import *
from src.model import *
from src.dataset import *
from src.metric import *
from src.utils.util_data import batch_to_cuda
from src.data import *


class MM2Seq(Encoder2Decoder):

    def __init__(self, config: Dict) -> None:
        LOGGER.debug('building {}...'.format(self.__class__.__name__))
        super(MM2Seq, self).__init__(
            encoder=MMEncoder_EmbRNN.load_from_config(config),
            decoder=SeqDecoder.load_from_config(config, modal='comment'),
        )
        self.config = config

    def eval_pipeline(self, batch_data: Dict, ) -> Tuple:

        enc_output, dec_hidden, enc_mask = self.encoder.forward(batch_data)
        sample_opt = {  'sample_max': 1, 'seq_length': self.config['training']['max_predict_length']}
        comment_pred, comment_logprobs, _, _ = \
            self.decoder.sample(batch_data, enc_output, dec_hidden, enc_mask, sample_opt)

        return comment_pred, comment_logprobs  # , comment_target_padded,

    def train_sl(self, batch: Dict, criterion: BaseLoss, ) -> Any:

        enc_output, dec_hidden, enc_mask = self.encoder.forward(batch)
        sample_opt = {'sample_max': 1, 'seq_length': self.config['training']['max_predict_length']}
        _, comment_logprobs, _, _, _, _, _, = self.decoder.forward(batch, enc_output, dec_hidden, enc_mask, sample_opt)

        if self.config['training']['pointer']:
            comment_target = batch['pointer'][1][:, :self.config['training']['max_predict_length']]
        else:
            comment_target = batch['comment'][2][:, :self.config['training']['max_predict_length']]

        loss = criterion(comment_logprobs, comment_target)

        return loss

    def train_sc(self, batch: Dict, criterion: BaseLoss, token_dicts: TokenDicts, reward_func: str, ) -> Any:
        if self.config['training']['pointer']:
            code_dict_comment, comment_extend_vocab, pointer_extra_zeros, code_oovs = batch['pointer']
        else:
            code_oovs = None

        enc_output, dec_hidden, enc_mask = self.encoder.forward(batch)
        sample_opt = {'sample_max': 0, 'seq_length': self.config['training']['max_predict_length']}

        comment, comment_logprobs, comment_logp_gathered, comment_padding_mask, reward, comment_lprob_sum, _, _, \
            = self.decoder.forward_pg(batch, enc_output, dec_hidden, enc_mask, token_dicts, sample_opt, reward_func,
                                      code_oovs)

        with torch.autograd.no_grad():
            sample_opt = {'sample_max': 1, 'seq_length': self.config['training']['max_predict_length']}
            comment2, comment_logprobs2, comment_logp2_gathered, comment_padding_mask2, reward2, comment_lprob_sum, _, _, = \
                self.decoder.forward_pg(batch, enc_output, dec_hidden, enc_mask, token_dicts, sample_opt, reward_func,
                                        code_oovs)  # 100x9,100x9

        rl_loss = criterion(comment_logprobs, comment, comment_padding_mask, (reward - reward2))
        rl_loss = rl_loss / torch.sum(comment_padding_mask).float()  # comment.data.ne(data.Constants.PAD)

        return rl_loss
